from datetime import UTC, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_serializer,
)

from app.schemas.base import ORMModel, UtcModel


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
