from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import InvoiceStatus, Product, SalesInvoice, User
from app.schemas.common import (
    DashboardBreakdown,
    DashboardDailyMetric,
    DashboardFinancialMetrics,
    DashboardSummary,
    InvoiceOut,
)
from app.services.after_sale import after_sales_for_invoices

router = APIRouter(prefix="/dashboard", tags=["Painel"])
BRAZIL_TZ = timezone(timedelta(hours=-3))


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
    _: User = Depends(get_current_user),
) -> DashboardSummary:
    _, _, since, until = _period(start_date, end_date)
    invoice_date = func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at)
    month_filter = (
        SalesInvoice.status == InvoiceStatus.confirmed,
        invoice_date >= since,
        invoice_date < until,
    )
    revenue = db.scalar(select(func.coalesce(func.sum(SalesInvoice.total), 0)).where(*month_filter))
    sales = db.scalar(select(func.count(SalesInvoice.id)).where(*month_filter)) or 0
    cancelled_filter = (
        SalesInvoice.status == InvoiceStatus.cancelled,
        invoice_date >= since,
        invoice_date < until,
    )
    cancelled_sales = db.scalar(select(func.count(SalesInvoice.id)).where(*cancelled_filter)) or 0
    cancelled_amount = db.scalar(
        select(func.coalesce(func.sum(SalesInvoice.total), 0)).where(*cancelled_filter)
    )
    products = db.scalar(select(func.count(Product.id)).where(Product.active.is_(True))) or 0
    low_stock = (
        db.scalar(
            select(func.count(Product.id)).where(
                Product.active.is_(True), Product.current_stock <= Product.minimum_stock
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
    return DashboardSummary(
        revenue_month=Decimal(str(revenue or 0)),
        confirmed_sales=sales,
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
    _: User = Depends(get_current_user),
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
    revenue = sum((invoice.total for invoice in current), Decimal("0"))
    previous_revenue = sum((invoice.total for invoice in previous), Decimal("0"))
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
        source_totals[label] = (amount + invoice.total, count + 1)
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
                amount=sum((invoice.total for invoice in day_rows), Decimal("0")),
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
