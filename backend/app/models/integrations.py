from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, new_id, now_utc
from app.models.catalog import (
    Product,
)
from app.models.purchases import PurchaseCase
from app.models.sales import (
    SalesInvoice,
)
from app.models.telemetry import HealthSnapshot, TelemetryEvent  # noqa: F401  (reexportado)
from app.models.users import User


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
