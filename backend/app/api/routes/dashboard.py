from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

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
from app.services.marketplace_costs import revenue_by_invoice, revenue_totals

router = APIRouter(prefix="/dashboard", tags=["Painel"])
BRAZIL_TZ = timezone(timedelta(hours=-3))
PENDING_SHIPMENT_STATUS = "ready_to_ship"
INACTIVE_ORDER_STATUSES = ("cancelled", "canceled", "in_cancel")
DISPATCHED_SHIPPING_SUBSTATUSES = (
    "picked_up",
    "shipped_to_carrier",
    "dropped_off",
    "in_transit",
    "in_hub",
    "on_route",
    "out_for_delivery",
    "at_the_branch",
    "delivered",
    "returned",
    "not_delivered",
)


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


@router.get("/summary", response_model=DashboardSummary)
def summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
) -> DashboardSummary:
    _, _, since, until = _period(start_date, end_date)
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    month_filter = (
        SalesInvoice.status == InvoiceStatus.confirmed,
        invoice_date >= since,
        invoice_date < until,
    )
    confirmed_invoices = list(db.scalars(select(SalesInvoice).where(*month_filter)))
    revenue_summary = revenue_totals(
        list(revenue_by_invoice(db, confirmed_invoices).values())
    )
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
    shipping_substatus = func.lower(func.coalesce(MarketplaceOrder.shipping_substatus, ""))
    sales_to_ship = (
        db.scalar(
            select(func.count(MarketplaceOrder.id)).where(
                MarketplaceOrder.shipping_status == PENDING_SHIPMENT_STATUS,
                MarketplaceOrder.status.not_in(INACTIVE_ORDER_STATUSES),
                shipping_substatus.not_in(DISPATCHED_SHIPPING_SUBSTATUSES),
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
    )


@router.get("/financial", response_model=DashboardFinancialMetrics)
def financial_metrics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DASHBOARD_READ)),
) -> DashboardFinancialMetrics:
    start, end, since, until = _period(start_date, end_date)
    duration = until - since
    previous_start = since - duration
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    rows = list(
        db.scalars(
            select(SalesInvoice)
            .options(selectinload(SalesInvoice.documents))
            .where(invoice_date >= previous_start, invoice_date < until)
        )
    )

    def timestamp(invoice: SalesInvoice) -> datetime:
        value = invoice.issued_at or invoice.created_at
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    current = [
        invoice
        for invoice in rows
        if since <= timestamp(invoice) < until and invoice.status == InvoiceStatus.confirmed
    ]
    previous = [
        invoice
        for invoice in rows
        if previous_start <= timestamp(invoice) < since
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
    daily: list[DashboardDailyMetric] = []
    first_day = start
    for offset in range((end - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        day_rows = [
            invoice for invoice in current if timestamp(invoice).astimezone(BRAZIL_TZ).date() == day
        ]
        daily.append(
            DashboardDailyMetric(
                date=day.isoformat(),
                label=day.strftime("%d/%m"),
                amount=sum((revenues[invoice.id].net for invoice in day_rows), Decimal("0")),
                count=len(day_rows),
            )
        )
    cancelled_count = sum(
        1
        for invoice in rows
        if since <= timestamp(invoice) < until and invoice.status == InvoiceStatus.cancelled
    )
    cancelled_amount = sum(
        (
            invoice.total
            for invoice in rows
            if since <= timestamp(invoice) < until and invoice.status == InvoiceStatus.cancelled
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
        daily=daily,
    )
