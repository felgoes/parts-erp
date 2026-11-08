from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import InvoiceStatus, MarketplaceOrder, Product, SalesInvoice, User
from app.schemas.common import (
    DashboardBreakdown,
    DashboardDailyMetric,
    DashboardFinancialMetrics,
    DashboardSummary,
    InvoiceOut,
)
from app.services.after_sale import after_sales_for_invoices
from app.services.invoice_tracking import attach_invoice_tracking
from app.services.marketplace_costs import InvoiceRevenue, revenue_by_invoice, revenue_totals
from app.services.shipping_status import pending_dispatch_filters

router = APIRouter(prefix="/dashboard", tags=["Painel"])
BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


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


@router.get("/summary", response_model=DashboardSummary)
def summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
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
    recent = list(
        db.scalars(
            select(SalesInvoice)
            .options(
                selectinload(SalesInvoice.customer),
                selectinload(SalesInvoice.documents),
                selectinload(SalesInvoice.items),
            )
            .where(invoice_date >= since, invoice_date < until)
            .order_by(SalesInvoice.created_at.desc())
            .limit(5)
        )
    )
    after_sales = after_sales_for_invoices(db, recent)
    recent_outputs: list[InvoiceOut] = []
    for invoice in recent:
        output = InvoiceOut.model_validate(invoice)
        output.after_sale = after_sales.get(invoice.id)
        recent_outputs.append(output)
    attach_invoice_tracking(db, recent_outputs)
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
        recent_invoices=recent_outputs,
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
