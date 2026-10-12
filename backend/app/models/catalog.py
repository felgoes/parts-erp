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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, new_id
from app.models.telemetry import HealthSnapshot, TelemetryEvent  # noqa: F401  (reexportado)


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
    stock_type: Mapped[str] = mapped_column(
        String(20), default="product", server_default="product", index=True
    )
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
    brand: Mapped[str | None] = mapped_column(String(120))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    mpn: Mapped[str | None] = mapped_column(String(120))
    barcode: Mapped[str | None] = mapped_column(String(32))
    category_id: Mapped[str | None] = mapped_column(String(80))
    condition: Mapped[str] = mapped_column(String(20), default="new")
    warranty: Mapped[str | None] = mapped_column(String(160))
    origin: Mapped[str | None] = mapped_column(String(80))
    weight_g: Mapped[int | None] = mapped_column()
    package_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    package_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    package_height_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    attributes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    fitments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    images: Mapped[list[str]] = mapped_column(JSON, default=list)
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
    category_id: Mapped[str | None] = mapped_column(String(80))
    sync_status: Mapped[str] = mapped_column(String(30), default="published")
    sync_error: Mapped[str | None] = mapped_column(Text)
    channel_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    product: Mapped[Product] = relationship(back_populates="listings")
