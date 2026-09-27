from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import InvoiceStatus, Product, SalesInvoice, User
from app.schemas.common import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Painel"])


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
        db.scalars(select(SalesInvoice).order_by(SalesInvoice.created_at.desc()).limit(5))
    )
    return DashboardSummary(
        revenue_month=Decimal(str(revenue or 0)),
        confirmed_sales=sales,
        products_count=products,
        low_stock_count=low_stock,
        recent_invoices=recent,
    )
