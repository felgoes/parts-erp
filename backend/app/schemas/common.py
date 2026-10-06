from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.models import UserRole


class UtcModel(BaseModel):
    @field_serializer("*", when_used="json")
    def serialize_utc_datetimes(self, value: Any) -> Any:
        """SQLite stores our UTC timestamps without tzinfo; make that explicit in JSON."""
        if isinstance(value, datetime):
            normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
            return normalized.isoformat().replace("+00:00", "Z")
        return value


class ORMModel(UtcModel):
    model_config = ConfigDict(from_attributes=True)


class ErpSettingsOut(BaseModel):
    company_name: str
    company_short_name: str
    logo_data_url: str | None
    backup_enabled: bool
    backup_frequency: Literal["daily", "weekly"]
    backup_retention_days: int
    backup_destination: Literal["google_drive"]
    backup_ready: bool = False
    backup_status: str = "setup_required"


class ErpSettingsUpdate(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    company_short_name: str = Field(min_length=1, max_length=40)
    logo_data_url: str | None = Field(default=None, max_length=3_000_000)
    backup_enabled: bool = False
    backup_frequency: Literal["daily", "weekly"] = "daily"
    backup_retention_days: int = Field(default=30, ge=1, le=30)
    backup_destination: Literal["google_drive"] = "google_drive"


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    active: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: UserRole = UserRole.operator


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class UserProfileUpdate(BaseModel):
    email: EmailStr


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    password: str | None = Field(default=None, min_length=12, max_length=128)
    role: UserRole | None = None
    active: bool | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user: UserOut


class BiometricCredentialCreate(BaseModel):
    device_name: str = Field(min_length=1, max_length=160)


class BiometricCredentialLogin(BaseModel):
    credential: str = Field(min_length=32, max_length=512)


class BiometricCredentialOut(BaseModel):
    credential: str
    expires_at: datetime


class PushDeviceRegistration(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    platform: Literal["android"] = "android"


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=160)
    manufacturer_part_number: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=160)
    item_condition: Literal["new", "used", "refurbished"] = "new"
    warranty_days: int | None = Field(default=None, ge=0, le=3650)
    origin_country: str | None = Field(default=None, max_length=80)
    weight_g: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_length_cm: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    package_width_cm: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    package_height_cm: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    attributes: dict[str, Any] = Field(default_factory=dict, max_length=100)
    fitments: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    sale_price: Decimal = Field(default=Decimal("0"), ge=0)
    cost_price: Decimal = Field(default=Decimal("0"), ge=0)
    current_stock: Decimal = Field(default=Decimal("0"))
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)
    active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=160)
    manufacturer_part_number: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=160)
    item_condition: Literal["new", "used", "refurbished"] | None = None
    warranty_days: int | None = Field(default=None, ge=0, le=3650)
    origin_country: str | None = Field(default=None, max_length=80)
    weight_g: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_length_cm: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    package_width_cm: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    package_height_cm: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    attributes: dict[str, Any] | None = Field(default=None, max_length=100)
    fitments: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    sale_price: Decimal | None = Field(default=None, ge=0)
    cost_price: Decimal | None = Field(default=None, ge=0)
    minimum_stock: Decimal | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductOut(ORMModel):
    id: str
    sku: str
    name: str
    description: str | None
    brand: str | None = None
    manufacturer: str | None = None
    manufacturer_part_number: str | None = None
    barcode: str | None = None
    category: str | None = None
    item_condition: str = "new"
    warranty_days: int | None = None
    origin_country: str | None = None
    weight_g: Decimal | None = None
    package_length_cm: Decimal | None = None
    package_width_cm: Decimal | None = None
    package_height_cm: Decimal | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fitments: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    sale_price: Decimal
    cost_price: Decimal | None = None
    current_stock: Decimal
    minimum_stock: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductListingOut(ORMModel):
    id: str
    provider: str
    external_item_id: str | None
    title: str | None
    permalink: str | None
    thumbnail: str | None
    images: list
    marketplace_price: Decimal | None
    available_quantity: Decimal | None
    sold_quantity: int | None
    visits: int | None
    status: str | None
    sync_status: str = "imported"
    sync_error: str | None = None
    category_id: str | None = None
    channel_data: dict[str, Any] = Field(default_factory=dict)
    synchronized_at: datetime | None


class ProductChannelDraftIn(BaseModel):
    category_id: str = Field(min_length=2, max_length=80)
    title: str | None = Field(default=None, max_length=200)
    family_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    listing_type_id: str | None = Field(default=None, max_length=60)
    item_condition: Literal["new", "used", "refurbished"] | None = None
    attributes: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    sale_terms: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    shipping: dict[str, Any] = Field(default_factory=dict, max_length=30)
    logistic_info: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


class ProductChannelMetadataOut(BaseModel):
    provider: str
    connected: bool
    user_product_seller: bool = False
    categories: list[dict[str, Any]] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    sale_terms: list[dict[str, Any]] = Field(default_factory=list)
    listing_types: list[dict[str, Any]] = Field(default_factory=list)
    logistics: list[dict[str, Any]] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)


class ProductDetailOut(ProductOut):
    listings: list[ProductListingOut]


class StockMovementOut(ORMModel):
    id: str
    product_id: str
    movement_type: str
    quantity: Decimal
    balance_after: Decimal
    unit_cost: Decimal | None
    movement_value: Decimal | None
    reason: str
    reference: str | None
    created_at: datetime


class FinanceProductMetric(BaseModel):
    product_id: str
    sku: str
    name: str
    current_stock: Decimal
    average_cost: Decimal
    inventory_value: Decimal
    inbound_quantity: Decimal
    inbound_value: Decimal
    outbound_quantity: Decimal
    outbound_value: Decimal
    return_quantity: Decimal
    return_value: Decimal
    net_cost_of_goods: Decimal


class FinanceDailyMetric(BaseModel):
    date: date
    label: str
    inbound_value: Decimal
    outbound_value: Decimal
    return_value: Decimal
    revenue: Decimal


class FinanceOverview(BaseModel):
    period_label: str
    inventory_units: Decimal
    inventory_value: Decimal
    inbound_quantity: Decimal
    inbound_value: Decimal
    outbound_quantity: Decimal
    outbound_value: Decimal
    return_quantity: Decimal
    return_value: Decimal
    net_cost_of_goods: Decimal
    revenue: Decimal
    gross_margin: Decimal | None
    gross_margin_percent: Decimal | None
    known_movements: int
    unknown_cost_movements: int
    unvalued_sales_items: int
    by_product: list[FinanceProductMetric]
    daily: list[FinanceDailyMetric]


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
    brand: str | None = None
    manufacturer_part_number: str | None = None
    barcode: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fitments: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    sale_price: Decimal
    in_stock: bool
    listings: list[CatalogListingOut] = Field(default_factory=list)


class StockAdjustment(BaseModel):
    quantity: Decimal
    reason: str = Field(min_length=3, max_length=255)


class PurchaseItemCreate(BaseModel):
    product_id: str | None = None
    sku: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=2, max_length=200)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)


class PurchaseCreate(BaseModel):
    needed_by: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    items: list[PurchaseItemCreate] = Field(min_length=1, max_length=100)


class PurchaseQuoteCreate(BaseModel):
    supplier_name: str = Field(min_length=2, max_length=200)
    supplier_contact: str | None = Field(default=None, max_length=200)
    total: Decimal = Field(ge=0)
    item_costs: dict[str, Decimal] = Field(min_length=1)
    delivery_days: int | None = Field(default=None, ge=0, le=3650)
    payment_terms: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("item_costs")
    @classmethod
    def validate_item_costs(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(cost < 0 for cost in value.values()):
            raise ValueError("O custo cotado não pode ser negativo")
        return value


class PurchaseReceiveItem(BaseModel):
    item_id: str
    receipt_id: str = Field(min_length=12, max_length=120)
    quantity: Decimal = Field(gt=0)
    product_id: str | None = None
    create_product: bool = False


class PurchaseReceive(BaseModel):
    items: list[PurchaseReceiveItem] = Field(min_length=1)


class PurchaseItemOut(ORMModel):
    id: str
    product_id: str | None
    sku: str
    description: str
    quantity: Decimal
    received_quantity: Decimal
    unit_cost: Decimal | None = None


class PurchaseQuoteOut(ORMModel):
    id: str
    supplier_name: str
    supplier_contact: str | None
    total: Decimal | None = None
    item_costs: dict[str, Decimal] | None = None
    delivery_days: int | None
    payment_terms: str | None
    notes: str | None
    created_at: datetime


class PurchaseEventOut(ORMModel):
    id: str
    event_type: str
    detail: str
    created_at: datetime


class PurchaseOut(ORMModel):
    id: str
    number: str
    status: str
    selected_quote_id: str | None
    needed_by: datetime | None
    ordered_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[PurchaseItemOut]
    quotes: list[PurchaseQuoteOut]
    events: list[PurchaseEventOut]


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


class CustomerPurchaseOut(UtcModel):
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


class InvoiceTrackingEventOut(UtcModel):
    status: str
    detail: str | None
    created_at: datetime


class InvoiceTrackingOut(UtcModel):
    shipment_id: str | None
    status: str | None
    shipping_status: str | None
    label_status: str | None
    last_update: datetime | None
    history: list[InvoiceTrackingEventOut]


class InvoiceAfterSaleOut(UtcModel):
    kind: str
    status: str
    reason: str | None = None
    requested_by: str | None = None
    return_id: str | None = None
    payment_status: str | None = None
    refund_amount: Decimal | None = None
    requested_at: datetime | None = None
    history: list[InvoiceTrackingEventOut] = Field(default_factory=list)
    cases: list["AfterSaleCaseOut"] = Field(default_factory=list)


class AfterSaleCaseEventOut(ORMModel):
    event_type: str
    status: str
    detail: str | None = None
    created_at: datetime


class AfterSaleCaseItemOut(ORMModel):
    id: str
    invoice_item_id: str | None
    product_id: str
    sku: str
    description: str
    requested_quantity: Decimal
    received_quantity: Decimal
    inspected_quantity: Decimal
    restocked_quantity: Decimal
    disposition: str
    notes: str | None = None


class AfterSaleCaseOut(ORMModel):
    id: str
    provider: str
    external_case_id: str
    marketplace_order_id: str
    invoice_id: str | None
    kind: str
    workflow_status: str
    marketplace_status: str
    reason: str | None
    requested_by: str | None
    payment_status: str | None
    refund_amount: Decimal | None
    requested_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    items: list[AfterSaleCaseItemOut]
    events: list[AfterSaleCaseEventOut]


class AfterSaleReceiveItemIn(BaseModel):
    item_id: str
    received_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class AfterSaleReceiveIn(BaseModel):
    items: list[AfterSaleReceiveItemIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=500)


class AfterSaleInspectItemIn(BaseModel):
    item_id: str
    restock_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    disposition: Literal["restock", "mixed", "damaged", "discarded"]
    notes: str | None = Field(default=None, max_length=500)


class AfterSaleInspectIn(BaseModel):
    items: list[AfterSaleInspectItemIn] = Field(min_length=1)


class AfterSaleCloseIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


class MarketStudyCreate(BaseModel):
    search_term: str = Field(min_length=2, max_length=200)
    sku: str | None = Field(default=None, max_length=80)
    category_id: str | None = Field(default=None, max_length=40)
    landed_cost: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    target_margin_pct: Decimal = Field(
        default=Decimal("25"), ge=0, lt=80, max_digits=5, decimal_places=2
    )
    marketplace_fee_pct: Decimal = Field(
        default=Decimal("16"), ge=0, lt=80, max_digits=5, decimal_places=2
    )
    shipping_cost: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)

    @field_validator("search_term")
    @classmethod
    def trim_search_term(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Informe o nome ou código da peça")
        return normalized

    @model_validator(mode="after")
    def validate_price_scenario(self) -> "MarketStudyCreate":
        if self.target_margin_pct + self.marketplace_fee_pct >= 100:
            raise ValueError("Taxa do canal e margem desejada precisam somar menos de 100%")
        return self


class MarketStudyConnectorUpdate(BaseModel):
    provider: Literal["openai_responses", "openai_compatible"]
    model: str = Field(min_length=1, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    enabled: bool = True


class MarketStudyConnectorOut(BaseModel):
    provider: str
    model: str
    base_url: str | None
    enabled: bool
    configured: bool
    has_api_key: bool


class MarketStudyOut(ORMModel):
    id: str
    created_by_id: str
    search_term: str
    sku: str | None
    category_id: str | None
    landed_cost: Decimal
    target_margin_pct: Decimal
    marketplace_fee_pct: Decimal
    shipping_cost: Decimal
    status: str
    provider_used: str | None
    result: dict[str, Any]
    linked_purchase_id: str | None
    created_at: datetime


class MarketStudyPurchaseIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


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
    shipping_substatus: str | None = None
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
