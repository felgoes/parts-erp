from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.schemas.base import ORMModel


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=160)
    manufacturer_part_number: str | None = Field(default=None, max_length=120)
    barcode: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=160)
    stock_type: Literal["product", "warehouse"] = "product"
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
    stock_type: Literal["product", "warehouse"] | None = None
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
    stock_type: Literal["product", "warehouse"] = "product"
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

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_legacy_attributes(cls, value: Any) -> dict[str, Any]:
        """Keep older marketplace imports with list attributes readable."""
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            normalized: dict[str, Any] = {}
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("id")
                attribute_value = item.get("value") or item.get("value_name")
                if name and attribute_value is not None:
                    normalized[str(name)] = attribute_value
            return normalized
        return {}


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
    gross_revenue: Decimal
    marketplace_fee_amount: Decimal
    marketplace_shipping_amount: Decimal
    marketplace_costs_pending: int
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
