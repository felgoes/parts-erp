from datetime import UTC, date, datetime, time, timedelta, tzinfo
from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.periods import BRAZIL_TZ as FIXED_BRAZIL_TZ
from app.core.permissions import Permission
from app.core.queue import get_queue_pool
from app.db.session import get_db
from app.models import (
    AdDailyMetric,
    InvoiceStatus,
    MarketplaceAccount,
    MarketplaceDashboardSync,
    MarketplaceOrder,
    Product,
    SalesInvoice,
    User,
)
from app.schemas.common import (
    DashboardBreakdown,
    DashboardDailyMetric,
    DashboardFinancialMetrics,
    DashboardSummary,
    InvoiceOut,
)
from app.schemas.dashboard import DashboardSalesPage
from app.services.after_sale import after_sales_for_invoices
from app.services.dashboard_marketplace import dashboard_marketplace_metrics
from app.services.invoice_tracking import attach_invoice_tracking
from app.services.marketplace_costs import InvoiceRevenue, revenue_by_invoice, revenue_totals
from app.services.shipping_status import pending_dispatch_filters

router = APIRouter(prefix="/dashboard", tags=["Painel"])
try:
    BRAZIL_TZ: tzinfo = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # O Termux pode não ter a base IANA instalada.
    BRAZIL_TZ = FIXED_BRAZIL_TZ


def _period(
    start_date: date | None, end_date: date | None
) -> tuple[date, date, datetime, datetime]:
    today = datetime.now(BRAZIL_TZ).date()
    start = start_date or today.replace(day=1)
    end = end_date or today
    if start > end:
        raise HTTPException(status_code=422, detail="A data inicial deve ser anterior à data final")
    if (end - start).days > 364:
        raise HTTPException(status_code=422, detail="O período máximo é de 365 dias")
    since = datetime.combine(start, time.min, BRAZIL_TZ).astimezone(UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, BRAZIL_TZ).astimezone(UTC)
    return start, end, since, until


def _timestamp(invoice: SalesInvoice) -> datetime:
    value = invoice.issued_at or invoice.created_at
    # SQLite removes timezone metadata when reading back a persisted UTC timestamp.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _daily_metrics(
    start: date, end: date, invoices: list[SalesInvoice], revenues: dict[str, InvoiceRevenue]
) -> list[DashboardDailyMetric]:
    buckets: dict[date, tuple[Decimal, int]] = {}
    for invoice in invoices:
        day = _timestamp(invoice).astimezone(BRAZIL_TZ).date()
        amount, count = buckets.get(day, (Decimal("0"), 0))
        buckets[day] = (amount + revenues[invoice.id].net, count + 1)
    daily = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        amount, count = buckets.get(day, (Decimal("0"), 0))
        daily.append(
            DashboardDailyMetric(
                date=day.isoformat(), label=day.strftime("%d/%m"), amount=amount, count=count
            )
        )
    return daily


RECENT_SALES_PAGE_SIZE = 10


def _recent_sales(
    db: Session, since: datetime, until: datetime, offset: int, page_size: int = 10
) -> DashboardSalesPage:
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    recent = list(
        db.scalars(
            select(SalesInvoice)
            .options(
                selectinload(SalesInvoice.customer),
                selectinload(SalesInvoice.documents),
                selectinload(SalesInvoice.items),
            )
            .where(invoice_date >= since, invoice_date < until)
            .order_by(invoice_date.desc(), SalesInvoice.created_at.desc(), SalesInvoice.id.desc())
            .offset(offset)
            .limit(page_size + 1)
        )
    )
    has_more = len(recent) > page_size
    recent = recent[:page_size]
    after_sales = after_sales_for_invoices(db, recent)
    recent_outputs: list[InvoiceOut] = []
    for invoice in recent:
        output = InvoiceOut.model_validate(invoice)
        output.after_sale = after_sales.get(invoice.id)
        recent_outputs.append(output)
    attach_invoice_tracking(db, recent_outputs)
    return DashboardSalesPage(
        items=recent_outputs,
        next_offset=offset + page_size if has_more else None,
    )


@router.get("/recent-sales", response_model=DashboardSalesPage)
def recent_sales(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
    page_size: Annotated[int, Query(ge=1, le=10)] = RECENT_SALES_PAGE_SIZE,
) -> DashboardSalesPage:
    _, _, since, until = _period(start_date, end_date)
    return _recent_sales(db, since, until, offset, page_size)


@router.get("/summary", response_model=DashboardSummary)
def summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
    recent_sales_offset: Annotated[int, Query(ge=0)] = 0,
    recent_sales_page_size: Annotated[int, Query(ge=1, le=10)] = RECENT_SALES_PAGE_SIZE,
) -> DashboardSummary:
    start, end, since, until = _period(start_date, end_date)
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    month_filter = (
        SalesInvoice.status == InvoiceStatus.confirmed,
        invoice_date >= since,
        invoice_date < until,
    )
    confirmed_invoices = list(db.scalars(select(SalesInvoice).where(*month_filter)))
    revenues = revenue_by_invoice(db, confirmed_invoices)
    revenue_summary = revenue_totals(list(revenues.values()))
    revenue = revenue_summary.net
    sales = len(confirmed_invoices)
    cancelled_filter = (
        SalesInvoice.status == InvoiceStatus.cancelled,
        invoice_date >= since,
        invoice_date < until,
    )
    cancelled_sales = db.scalar(select(func.count(SalesInvoice.id)).where(*cancelled_filter)) or 0
    cancelled_amount = db.scalar(
        select(func.coalesce(func.sum(SalesInvoice.total), 0)).where(*cancelled_filter)
    )
    sales_to_ship = (
        db.scalar(
            select(func.count(MarketplaceOrder.id)).where(
                *pending_dispatch_filters(),
            )
        )
        or 0
    )
    products = db.scalar(select(func.count(Product.id)).where(Product.active.is_(True))) or 0
    low_stock = (
        db.scalar(
            select(func.count(Product.id)).where(
                Product.active.is_(True),
                Product.stock_type == "product",
                Product.current_stock < Product.minimum_stock,
            )
        )
        or 0
    )
    recent = _recent_sales(db, since, until, recent_sales_offset, recent_sales_page_size)
    return DashboardSummary(
        revenue_month=Decimal(str(revenue or 0)),
        gross_revenue_month=revenue_summary.gross,
        marketplace_fee_amount=revenue_summary.marketplace_fees,
        marketplace_shipping_amount=revenue_summary.seller_shipping,
        marketplace_costs_pending=revenue_summary.costs_pending,
        confirmed_sales=sales,
        sales_to_ship=sales_to_ship,
        cancelled_sales=cancelled_sales,
        cancelled_amount=Decimal(str(cancelled_amount or 0)),
        products_count=products,
        low_stock_count=low_stock,
        recent_invoices=recent.items,
        recent_sales_next_offset=recent.next_offset,
        daily=_daily_metrics(start, end, confirmed_invoices, revenues),
    )


@router.get("/financial", response_model=DashboardFinancialMetrics)
def financial_metrics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
) -> DashboardFinancialMetrics:
    start, end, since, until = _period(start_date, end_date)
    previous_day = start - timedelta(days=(end - start).days + 1)
    previous_start = datetime.combine(previous_day, time.min, BRAZIL_TZ).astimezone(UTC)
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    rows = list(
        db.scalars(
            select(SalesInvoice)
            .options(selectinload(SalesInvoice.documents))
            .where(invoice_date >= previous_start, invoice_date < until)
        )
    )

    current = [
        invoice
        for invoice in rows
        if since <= _timestamp(invoice) < until and invoice.status == InvoiceStatus.confirmed
    ]
    previous = [
        invoice
        for invoice in rows
        if previous_start <= _timestamp(invoice) < since
        and invoice.status == InvoiceStatus.confirmed
    ]
    revenues = revenue_by_invoice(db, rows)
    current_summary = revenue_totals([revenues[invoice.id] for invoice in current])
    previous_summary = revenue_totals([revenues[invoice.id] for invoice in previous])
    revenue = current_summary.net
    previous_revenue = previous_summary.net
    change = (
        ((revenue - previous_revenue) / previous_revenue * Decimal("100"))
        if previous_revenue
        else (Decimal("100") if revenue else Decimal("0"))
    )
    source_totals: dict[str, tuple[Decimal, int]] = {}
    for invoice in current:
        source = invoice.source.value if hasattr(invoice.source, "value") else str(invoice.source)
        label = "Mercado Livre" if source == "mercadolivre" else "Venda manual"
        amount, count = source_totals.get(label, (Decimal("0"), 0))
        source_totals[label] = (amount + revenues[invoice.id].net, count + 1)
    cancelled_count = sum(
        1
        for invoice in rows
        if since <= _timestamp(invoice) < until and invoice.status == InvoiceStatus.cancelled
    )
    cancelled_amount = sum(
        (
            invoice.total
            for invoice in rows
            if since <= _timestamp(invoice) < until and invoice.status == InvoiceStatus.cancelled
        ),
        Decimal("0"),
    )
    return DashboardFinancialMetrics(
        period_label=f"{start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}",
        revenue=revenue,
        gross_revenue=current_summary.gross,
        marketplace_fee_amount=current_summary.marketplace_fees,
        marketplace_shipping_amount=current_summary.seller_shipping,
        marketplace_costs_pending=current_summary.costs_pending,
        sales_count=len(current),
        average_ticket=(revenue / len(current) if current else Decimal("0")),
        previous_revenue=previous_revenue,
        revenue_change_percent=change.quantize(Decimal("0.01")),
        cancelled_count=cancelled_count,
        cancelled_amount=cancelled_amount,
        documents_count=sum(len(invoice.documents) for invoice in current),
        by_source=[
            DashboardBreakdown(label=label, amount=amount, count=count)
            for label, (amount, count) in source_totals.items()
        ],
        daily=_daily_metrics(start, end, current, revenues),
    )


@router.get("/mercadolivre")
def marketplace_dashboard(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
):
    start, end, _, _ = _period(start_date, end_date)
    return dashboard_marketplace_metrics(db, start, end)


@router.post("/mercadolivre/refresh", status_code=202)
async def refresh_marketplace_dashboard(
    start_date: date = Query(...),
    end_date: date = Query(...),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
):
    start, end, _, _ = _period(start_date, end_date)
    accounts = list(
        db.scalars(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "mercadolivre", MarketplaceAccount.active.is_(True)
            )
        )
    )
    if not accounts:
        return {"accepted": False, "status": "disconnected"}
    queue = await get_queue_pool()
    queued = 0
    for account in accounts:
        state = db.scalar(
            select(MarketplaceDashboardSync).where(
                MarketplaceDashboardSync.account_id == account.id,
                MarketplaceDashboardSync.period_start == start,
                MarketplaceDashboardSync.period_end == end,
            )
        )
        fresh = False
        if (
            state
            and not force
            and state.sync_status == "succeeded"
            and not state.partial
            and state.last_success_at
        ):
            last_success = state.last_success_at
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=UTC)
            fresh = datetime.now(UTC) - last_success < timedelta(minutes=5)
        if not fresh:
            if state is None:
                state = MarketplaceDashboardSync(
                    account_id=account.id,
                    period_start=start,
                    period_end=end,
                    sync_status="pending",
                    partial=False,
                    last_attempt_at=datetime.now(UTC),
                )
                db.add(state)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    state = db.scalar(
                        select(MarketplaceDashboardSync).where(
                            MarketplaceDashboardSync.account_id == account.id,
                            MarketplaceDashboardSync.period_start == start,
                            MarketplaceDashboardSync.period_end == end,
                        )
                    )
                    if state is None:
                        raise
            else:
                if state.sync_status not in {"pending", "running"}:
                    state.sync_status, state.sync_error = "pending", None
                    state.last_attempt_at = datetime.now(UTC)
                db.commit()
            job = await queue.enqueue_job(
                "sync_dashboard_marketplace_orders",
                account.id,
                start.isoformat(),
                end.isoformat(),
                _job_id=f"dashboard-ml-orders:{account.id}:{start.isoformat()}:{end.isoformat()}",
            )
            if job:
                queued += 1
        latest_metric = db.scalar(
            select(func.max(AdDailyMetric.synced_at)).where(
                AdDailyMetric.account_id == account.id, AdDailyMetric.channel == "mercadolivre"
            )
        )
        metric_at = (
            latest_metric.replace(tzinfo=UTC)
            if latest_metric and latest_metric.tzinfo is None
            else latest_metric
        )
        if metric_at is None or datetime.now(UTC) - metric_at >= timedelta(hours=6) or force:
            job = await queue.enqueue_job(
                "sync_mercadolivre_ad_metrics", account.id, _job_id=f"ad-metrics:{account.id}"
            )
            if job:
                queued += 1
    return {"accepted": True, "status": "queued" if queued else "already_queued"}
