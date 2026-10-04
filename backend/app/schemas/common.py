from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from app.models import UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    role: str


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = UserRole.operator


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    password: str | None = Field(default=None, min_length=12, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user: UserOut


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    sale_price: Decimal = Field(default=Decimal("0"), ge=0)
    cost_price: Decimal = Field(default=Decimal("0"), ge=0)
    current_stock: Decimal = Field(default=Decimal("0"))
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)
    active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    sale_price: Decimal | None = Field(default=None, ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)
    minimum_stock: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductOut(ORMModel):
    id: str
    sku: str
    name: str
    description: str | None
    sale_price: Decimal
    cost_price: Decimal
    current_stock: Decimal
    minimum_stock: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductListingOut(ORMModel):
    id: str
    provider: str
    external_item_id: str
    title: str | None
    permalink: str | None
    thumbnail: str | None
    images: list
    marketplace_price: Decimal | None
    available_quantity: Decimal | None
    sold_quantity: int | None
    visits: int | None
    status: str | None
    synchronized_at: datetime | None


class ProductDetailOut(ProductOut):
    listings: list[ProductListingOut]


class StockMovementOut(ORMModel):
    id: str
    product_id: str
    movement_type: str
    quantity: Decimal
    balance_after: Decimal
    reason: str
    reference: str | None
    created_at: datetime


class CatalogListingOut(BaseModel):
    provider: str
    external_item_id: str
    title: str | None
    permalink: str | None
    thumbnail: str | None
    images: list[str]
    marketplace_price: Decimal | None
    available_quantity: Decimal | None
    sold_quantity: int | None
    visits: int | None
    status: str | None
    attributes: list[dict[str, str]]
    synchronized_at: datetime | None


class CatalogProductOut(BaseModel):
    id: str
    sku: str
    name: str
    description: str | None
    sale_price: Decimal
    in_stock: bool
    listings: list[CatalogListingOut] = Field(default_factory=list)


class StockAdjustment(BaseModel):
    quantity: Decimal
    reason: str = Field(min_length=3, max_length=255)


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    document: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)


class CustomerOut(ORMModel):
    id: str
    name: str
    document: str | None
    email: str | None
    phone: str | None
    created_at: datetime


class CustomerPurchaseOut(BaseModel):
    id: str
    number: str
    status: str
    source: str
    marketplace_order_id: str | None
    total: Decimal
    issued_at: datetime | None
    created_at: datetime
    item_count: int

    @field_serializer("issued_at")
    def serialize_issued_at(self, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


class CustomerDetailOut(CustomerOut):
    purchase_count: int
    confirmed_purchase_count: int
    total_purchased: Decimal
    average_purchase: Decimal
    last_purchase_at: datetime | None
    marketplace_order_count: int
    cancelled_order_count: int
    purchases: list[CustomerPurchaseOut]


class InvoiceItemCreate(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)


class InvoiceCreate(BaseModel):
    customer_id: str | None = None
    items: list[InvoiceItemCreate] = Field(min_length=1)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    shipping: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None


class InvoiceItemOut(ORMModel):
    id: str
    product_id: str
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class DocumentOut(ORMModel):
    id: str
    document_type: str
    filename: str
    created_at: datetime


class InvoiceCustomerOut(ORMModel):
    name: str
    document: str | None = None
    email: str | None = None
    phone: str | None = None


class InvoiceTrackingEventOut(BaseModel):
    status: str
    detail: str | None
    created_at: datetime


class InvoiceTrackingOut(BaseModel):
    shipment_id: str | None
    status: str | None
    shipping_status: str | None
    label_status: str | None
    last_update: datetime | None
    history: list[InvoiceTrackingEventOut]


class InvoiceAfterSaleOut(BaseModel):
    kind: str
    status: str
    reason: str | None = None
    requested_by: str | None = None
    return_id: str | None = None
    payment_status: str | None = None
    refund_amount: Decimal | None = None
    requested_at: datetime | None = None
    history: list[InvoiceTrackingEventOut] = Field(default_factory=list)


class InvoiceOut(ORMModel):
    id: str
    number: str
    customer_id: str | None
    status: str
    source: str
    marketplace_order_id: str | None
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    total: Decimal
    issued_at: datetime | None
    notes: str | None
    created_at: datetime
    items: list[InvoiceItemOut]
    documents: list[DocumentOut]
    tracking: "InvoiceTrackingOut | None" = None
    after_sale: InvoiceAfterSaleOut | None = None
    customer: InvoiceCustomerOut | None = None

    @field_serializer("issued_at")
    def serialize_issued_at(self, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


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


class MarketplaceOrderOut(ORMModel):
    id: str
    external_order_id: str
    seller_id: str
    status: str
    sync_status: str
    sync_error: str | None
    invoice_id: str | None
    synchronized_at: datetime | None
    created_at: datetime
    provider: str = "mercadolivre"
    shipment_id: str | None = None
    shipping_status: str | None = None
    fiscal_status: str = "pending"
    fiscal_error: str | None = None
    external_invoice_id: str | None = None
    label_status: str = "pending"
    label_error: str | None = None
    automation_updated_at: datetime | None = None
    payload: dict | None = None
    invoice: InvoiceOut | None = None


class MarketplaceOrderEventOut(ORMModel):
    id: str
    order_id: str
    event_type: str
    status: str
    detail: str | None
    payload: dict
    created_at: datetime


class MarketplaceStatus(BaseModel):
    configured: bool
    connected: bool
    seller_id: str | None = None
    nickname: str | None = None
    token_expires_at: datetime | None = None
    auto_issue_invoice: bool = True
    auto_download_label: bool = True


class MarketplaceConfigOut(BaseModel):
    client_id: str
    client_secret_configured: bool
    redirect_uri: str
    site_id: str
    import_orders: bool
    automatic_stock: bool
    sync_documents: bool
    auto_issue_invoice: bool = True
    auto_download_label: bool = True


class MarketplaceConfigUpdate(BaseModel):
    client_id: str
    client_secret: str | None = None
    redirect_uri: str
    site_id: str = "MLB"
    import_orders: bool = True
    automatic_stock: bool = True
    sync_documents: bool = True
    auto_issue_invoice: bool = True
    auto_download_label: bool = True


class ShopeeStatus(BaseModel):
    configured: bool
    connected: bool
    shop_id: str | None = None
    token_expires_at: datetime | None = None


class ShopeeConfigOut(BaseModel):
    partner_id: str
    partner_key_configured: bool
    shop_id: str | None
    redirect_uri: str
    region: str
    import_orders: bool
    automatic_stock: bool
    sync_documents: bool


class ShopeeConfigUpdate(BaseModel):
    partner_id: str
    partner_key: str | None = None
    shop_id: str | None = None
    redirect_uri: str
    region: str = "BR"
    import_orders: bool = True
    automatic_stock: bool = True
    sync_documents: bool


class TelemetryEventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    source: str = Field(default="site", min_length=1, max_length=30)
    anonymous_id: str | None = Field(default=None, max_length=100)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=20)


class EventCount(BaseModel):
    name: str
    count: int


class TelemetryDailyCount(BaseModel):
    date: date
    events: list[EventCount] = Field(default_factory=list)


class ProductViewCount(BaseModel):
    sku: str
    product_name: str
    views: int


class TelemetryHealthOut(ORMModel):
    check_name: str
    ok: bool
    latency_ms: Decimal
    detail: str | None
    checked_at: datetime


class TelemetrySummary(BaseModel):
    days: int
    events: list[EventCount]
    daily_events: list[TelemetryDailyCount] = Field(default_factory=list)
    product_views: list[ProductViewCount] = Field(default_factory=list)
    health: list[TelemetryHealthOut]
