from decimal import Decimal

from pydantic import (
    BaseModel,
)

from app.schemas.invoices import (
    InvoiceOut,
)


class DashboardDailyMetric(BaseModel):
    date: str
    label: str
    amount: Decimal
    count: int


class DashboardSalesPage(BaseModel):
    items: list[InvoiceOut]
    next_offset: int | None


class DashboardSummary(BaseModel):
    revenue_month: Decimal
    gross_revenue_month: Decimal
    marketplace_fee_amount: Decimal
    marketplace_shipping_amount: Decimal
    marketplace_costs_pending: int
    confirmed_sales: int
    sales_to_ship: int
    cancelled_sales: int
    cancelled_amount: Decimal
    products_count: int
    low_stock_count: int
    recent_invoices: list[InvoiceOut]
    recent_sales_next_offset: int | None = None
    daily: list[DashboardDailyMetric]


class DashboardBreakdown(BaseModel):
    label: str
    amount: Decimal
    count: int


class DashboardFinancialMetrics(BaseModel):
    period_label: str
    revenue: Decimal
    gross_revenue: Decimal
    marketplace_fee_amount: Decimal
    marketplace_shipping_amount: Decimal
    marketplace_costs_pending: int
    sales_count: int
    average_ticket: Decimal
    previous_revenue: Decimal
    revenue_change_percent: Decimal
    cancelled_count: int
    cancelled_amount: Decimal
    documents_count: int
    by_source: list[DashboardBreakdown]
    daily: list[DashboardDailyMetric]
