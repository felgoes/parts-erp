import enum
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class UserRole(enum.StrEnum):
    admin = "admin"
    manager = "manager"
    operator = "operator"
    stock = "stock"
    finance = "finance"
    viewer = "viewer"


class InvoiceStatus(enum.StrEnum):
    draft = "draft"
    confirmed = "confirmed"
    cancelled = "cancelled"


class InvoiceSource(enum.StrEnum):
    manual = "manual"
    mercadolivre = "mercadolivre"
    shopee = "shopee"


class MovementType(enum.StrEnum):
    sale = "sale"
    cancellation = "cancellation"
    adjustment = "adjustment"
    purchase_received = "purchase_received"
    customer_return = "customer_return"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.operator)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_filename: Mapped[str | None] = mapped_column(String(80))


class ErpSettings(TimestampMixin, Base):
    """Singleton configuration for shared company identity and backup policy."""

    __tablename__ = "erp_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_name: Mapped[str] = mapped_column(String(120), default="Parts ERP")
    company_short_name: Mapped[str] = mapped_column(String(40), default="Parts")
    logo_data_url: Mapped[str | None] = mapped_column(Text)
    backup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    backup_retention_days: Mapped[int] = mapped_column(default=30)
    backup_destination: Mapped[str] = mapped_column(String(30), default="google_drive")


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(160))
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(32), index=True)
    category: Mapped[str | None] = mapped_column(String(160))
    item_condition: Mapped[str] = mapped_column(String(24), default="new")
    warranty_days: Mapped[int | None] = mapped_column()
    origin_country: Mapped[str | None] = mapped_column(String(80))
    weight_g: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    package_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    package_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    package_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fitments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    images: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    current_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    listings: Mapped[list["ProductMarketplaceListing"]] = relationship(
        cascade="all, delete-orphan", back_populates="product", lazy="selectin"
    )


class ProductMarketplaceListing(TimestampMixin, Base):
    __tablename__ = "product_marketplace_listings"
    __table_args__ = (
        Index("uq_product_marketplace_listing", "provider", "external_item_id", unique=True),
        Index("ix_product_marketplace_listing_product", "product_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(30), default="mercadolivre")
    external_item_id: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str | None] = mapped_column(String(200))
    permalink: Mapped[str | None] = mapped_column(String(1000))
    thumbnail: Mapped[str | None] = mapped_column(String(1000))
    images: Mapped[list[Any]] = mapped_column(JSON, default=list)
    marketplace_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    available_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    sold_quantity: Mapped[int | None] = mapped_column()
    visits: Mapped[int | None] = mapped_column()
    status: Mapped[str | None] = mapped_column(String(40))
    sync_status: Mapped[str] = mapped_column(String(30), default="imported")
    sync_error: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[str | None] = mapped_column(String(80))
    channel_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    synchronized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[Product] = relationship(back_populates="listings")


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), index=True)
    document: Mapped[str | None] = mapped_column(String(20), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    marketplace_buyer_id: Mapped[str | None] = mapped_column(String(80), unique=True)


class SalesInvoice(TimestampMixin, Base):
    __tablename__ = "sales_invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.draft)
    source: Mapped[InvoiceSource] = mapped_column(Enum(InvoiceSource), default=InvoiceSource.manual)
    marketplace_order_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    shipping: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(
        cascade="all, delete-orphan", back_populates="invoice", lazy="selectin"
    )
    documents: Mapped[list["InvoiceDocument"]] = relationship(
        cascade="all, delete-orphan", back_populates="invoice", lazy="selectin"
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("sales_invoices.id", ondelete="CASCADE"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    invoice: Mapped[SalesInvoice] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_product_created", "product_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    movement_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(String(255))
    reference: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    product: Mapped[Product] = relationship()


class PurchaseCase(TimestampMixin, Base):
    """A procurement cycle, from supplier negotiation through stock receipt."""

    __tablename__ = "purchase_cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="negotiating", index=True)
    selected_quote_id: Mapped[str | None] = mapped_column(String(36))
    needed_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list["PurchaseItem"]] = relationship(
        cascade="all, delete-orphan", back_populates="purchase", lazy="selectin"
    )
    quotes: Mapped[list["PurchaseQuote"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="purchase",
        lazy="selectin",
        foreign_keys="PurchaseQuote.purchase_id",
    )
    events: Mapped[list["PurchaseEvent"]] = relationship(
        cascade="all, delete-orphan", back_populates="purchase", lazy="selectin"
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_cases.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    purchase: Mapped[PurchaseCase] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class PurchaseQuote(TimestampMixin, Base):
    __tablename__ = "purchase_quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(
        ForeignKey("purchase_cases.id", ondelete="CASCADE"), index=True
    )
    supplier_name: Mapped[str] = mapped_column(String(200))
    supplier_contact: Mapped[str | None] = mapped_column(String(200))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    item_costs: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    delivery_days: Mapped[int | None] = mapped_column()
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    purchase: Mapped[PurchaseCase] = relationship(
        back_populates="quotes", foreign_keys=[purchase_id]
    )


class PurchaseEvent(Base):
    __tablename__ = "purchase_events"
    __table_args__ = (Index("ix_purchase_events_purchase_created", "purchase_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(ForeignKey("purchase_cases.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    purchase: Mapped[PurchaseCase] = relationship(back_populates="events")


class MarketStudyConnectorConfig(TimestampMixin, Base):
    __tablename__ = "market_study_connector_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40), default="openai_responses")
    base_url: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(120), default="gpt-6-luna")
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketStudy(TimestampMixin, Base):
    __tablename__ = "market_studies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    search_term: Mapped[str] = mapped_column(String(200), index=True)
    sku: Mapped[str | None] = mapped_column(String(80))
    category_id: Mapped[str | None] = mapped_column(String(40))
    landed_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    target_margin_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    marketplace_fee_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    provider_used: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    linked_purchase_id: Mapped[str | None] = mapped_column(ForeignKey("purchase_cases.id"))

    created_by: Mapped[User] = relationship()
    linked_purchase: Mapped[PurchaseCase | None] = relationship()


class MarketplaceAccount(TimestampMixin, Base):
    __tablename__ = "marketplace_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(30), default="mercadolivre")
    seller_id: Mapped[str] = mapped_column(String(80), unique=True)
    nickname: Mapped[str | None] = mapped_column(String(160))
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MarketplaceConfig(TimestampMixin, Base):
    __tablename__ = "marketplace_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(String(120), default="")
    encrypted_client_secret: Mapped[str | None] = mapped_column(Text)
    redirect_uri: Mapped[str | None] = mapped_column(String(500))
    site_id: Mapped[str] = mapped_column(String(20), default="MLB")
    import_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    automatic_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_documents: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_issue_invoice: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_download_label: Mapped[bool] = mapped_column(Boolean, default=True)


class ShopeeConfig(TimestampMixin, Base):
    __tablename__ = "shopee_config"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    partner_id: Mapped[str] = mapped_column(String(120), default="")
    encrypted_partner_key: Mapped[str | None] = mapped_column(Text)
    shop_id: Mapped[str | None] = mapped_column(String(80))
    redirect_uri: Mapped[str | None] = mapped_column(String(500))
    region: Mapped[str] = mapped_column(String(10), default="BR")
    import_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    automatic_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_documents: Mapped[bool] = mapped_column(Boolean, default=True)


class MarketplaceOrder(TimestampMixin, Base):
    __tablename__ = "marketplace_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(30), default="mercadolivre")
    external_order_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    seller_id: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(60))
    sync_status: Mapped[str] = mapped_column(String(30), default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("sales_invoices.id"), unique=True)
    synchronized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipment_id: Mapped[str | None] = mapped_column(String(80), index=True)
    shipping_status: Mapped[str | None] = mapped_column(String(60))
    shipping_substatus: Mapped[str | None] = mapped_column(String(80))
    fiscal_status: Mapped[str] = mapped_column(String(30), default="pending")
    fiscal_error: Mapped[str | None] = mapped_column(Text)
    external_invoice_id: Mapped[str | None] = mapped_column(String(80), index=True)
    label_status: Mapped[str] = mapped_column(String(30), default="pending")
    label_error: Mapped[str | None] = mapped_column(Text)
    automation_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    invoice: Mapped[SalesInvoice | None] = relationship()


class MarketplaceOrderEvent(Base):
    __tablename__ = "marketplace_order_events"
    __table_args__ = (Index("ix_marketplace_order_events_order_created", "order_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("marketplace_orders.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    order: Mapped[MarketplaceOrder] = relationship()


class AfterSaleCase(TimestampMixin, Base):
    """A marketplace return/claim linked to its original order and invoice."""

    __tablename__ = "after_sale_cases"
    __table_args__ = (
        UniqueConstraint("provider", "external_case_id", name="uq_after_sale_provider_external"),
        Index("ix_after_sale_invoice", "invoice_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(30), default="mercadolivre")
    external_case_id: Mapped[str] = mapped_column(String(100))
    marketplace_order_id: Mapped[str] = mapped_column(ForeignKey("marketplace_orders.id"))
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("sales_invoices.id"))
    kind: Mapped[str] = mapped_column(String(20), default="return")
    workflow_status: Mapped[str] = mapped_column(String(30), default="requested", index=True)
    marketplace_status: Mapped[str] = mapped_column(String(60), default="unknown")
    reason: Mapped[str | None] = mapped_column(String(500))
    requested_by: Mapped[str | None] = mapped_column(String(80))
    payment_status: Mapped[str | None] = mapped_column(String(40))
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    order: Mapped[MarketplaceOrder] = relationship()
    invoice: Mapped[SalesInvoice | None] = relationship()
    items: Mapped[list["AfterSaleCaseItem"]] = relationship(
        cascade="all, delete-orphan", back_populates="case", lazy="selectin"
    )
    events: Mapped[list["AfterSaleCaseEvent"]] = relationship(
        cascade="all, delete-orphan",
        back_populates="case",
        lazy="selectin",
        order_by="AfterSaleCaseEvent.created_at",
    )


class AfterSaleCaseItem(Base):
    __tablename__ = "after_sale_case_items"
    __table_args__ = (Index("ix_after_sale_case_items_case", "case_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("after_sale_cases.id", ondelete="CASCADE"))
    invoice_item_id: Mapped[str | None] = mapped_column(ForeignKey("invoice_items.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    sku: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200))
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    inspected_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    restocked_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    disposition: Mapped[str] = mapped_column(String(30), default="pending")
    notes: Mapped[str | None] = mapped_column(String(500))

    case: Mapped[AfterSaleCase] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class AfterSaleCaseEvent(Base):
    __tablename__ = "after_sale_case_events"
    __table_args__ = (
        Index("ix_after_sale_case_events_case_created", "case_id", "created_at"),
        UniqueConstraint("case_id", "fingerprint", name="uq_after_sale_case_event_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("after_sale_cases.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(String(500))
    fingerprint: Mapped[str] = mapped_column(String(180))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    case: Mapped[AfterSaleCase] = relationship(back_populates="events")


class InvoiceDocument(Base):
    __tablename__ = "invoice_documents"
    __table_args__ = (
        Index("uq_invoice_document_external", "invoice_id", "external_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("sales_invoices.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(120))
    document_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    invoice: Mapped[SalesInvoice] = relationship(back_populates="documents")


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (Index("ix_telemetry_events_name_created", "name", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(30), default="site")
    visitor_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HealthSnapshot(Base):
    __tablename__ = "health_snapshots"
    __table_args__ = (Index("ix_health_snapshots_checked_at", "checked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    check_name: Mapped[str] = mapped_column(String(60), index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    detail: Mapped[str | None] = mapped_column(String(255))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
