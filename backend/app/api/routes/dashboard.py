from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import InvoiceStatus, Product, SalesInvoice, User
from app.schemas.common import DashboardBreakdown, DashboardDailyMetric, DashboardFinancialMetrics, DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Painel"])
MONTHS_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> DashboardSummary:
    now = datetime.now(UTC)
    month_filter = (
        SalesInvoice.status == InvoiceStatus.confirmed,
        extract("year", SalesInvoice.issued_at) == now.year,
        extract("month", SalesInvoice.issued_at) == now.month,
    )
    revenue = db.scalar(select(func.coalesce(func.sum(SalesInvoice.total), 0)).where(*month_filter))
    sales = db.scalar(select(func.count(SalesInvoice.id)).where(*month_filter)) or 0
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
            .order_by(SalesInvoice.created_at.desc())
            .limit(5)
        )
    )
    return DashboardSummary(
        revenue_month=Decimal(str(revenue or 0)),
        confirmed_sales=sales,
        products_count=products,
        low_stock_count=low_stock,
        recent_invoices=recent,
    )


@router.get("/financial", response_model=DashboardFinancialMetrics)
def financial_metrics(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> DashboardFinancialMetrics:
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_start = (month_start - timedelta(days=1)).replace(day=1)
    rows = list(
        db.scalars(
            select(SalesInvoice)
            .options(selectinload(SalesInvoice.documents))
            .where(SalesInvoice.created_at >= previous_start)
        )
    )

    def timestamp(invoice: SalesInvoice) -> datetime:
        value = invoice.issued_at or invoice.created_at
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    current = [
        invoice
        for invoice in rows
        if month_start <= timestamp(invoice) <= now and invoice.status == InvoiceStatus.confirmed
    ]
    previous = [
        invoice
        for invoice in rows
        if previous_start <= timestamp(invoice) < month_start and invoice.status == InvoiceStatus.confirmed
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
    first_day = max(month_start, now - timedelta(days=13))
    for offset in range((now.date() - first_day.date()).days + 1):
        day = first_day.date() + timedelta(days=offset)
        day_rows = [invoice for invoice in current if timestamp(invoice).date() == day]
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
        if month_start <= timestamp(invoice) <= now and invoice.status == InvoiceStatus.cancelled
    )
    return DashboardFinancialMetrics(
        period_label=f"{MONTHS_PT[now.month - 1]} de {now.year}",
        revenue=revenue,
        sales_count=len(current),
        average_ticket=(revenue / len(current) if current else Decimal("0")),
        previous_revenue=previous_revenue,
        revenue_change_percent=change.quantize(Decimal("0.01")),
        cancelled_count=cancelled_count,
        documents_count=sum(len(invoice.documents) for invoice in current),
        by_source=[
            DashboardBreakdown(label=label, amount=amount, count=count)
            for label, (amount, count) in source_totals.items()
        ],
        daily=daily,
    )
