from decimal import Decimal

from pydantic import (
    BaseModel,
)

from app.schemas.invoices import (
    InvoiceOut,
)


class DashboardSummary(BaseModel):
    revenue_month: Decimal
    confirmed_sales: int
    cancelled_sales: int
    cancelled_amount: Decimal
    products_count: int
    low_stock_count: int
    recent_invoices: list[InvoiceOut]


class DashboardBreakdown(BaseModel):
    label: str
    amount: Decimal
    count: int


class DashboardDailyMetric(BaseModel):
    date: str
    label: str
    amount: Decimal
    count: int


class DashboardFinancialMetrics(BaseModel):
    period_label: str
    revenue: Decimal
    sales_count: int
    average_ticket: Decimal
    previous_revenue: Decimal
    revenue_change_percent: Decimal
    cancelled_count: int
    cancelled_amount: Decimal
    documents_count: int
    by_source: list[DashboardBreakdown]
    daily: list[DashboardDailyMetric]
