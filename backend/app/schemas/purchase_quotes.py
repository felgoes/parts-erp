"""Esquemas da cotação de compra e do item da compra.

Separados de `common.py` para os ajustes da cotação não fazerem o arquivo compartilhado
crescer. `common.py` reexporta estes nomes: nenhum importador precisou mudar.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import ORMModel


class PurchaseQuoteCreate(BaseModel):
    supplier_name: str = Field(min_length=2, max_length=200)
    supplier_contact: str | None = Field(default=None, max_length=200)
    total: Decimal = Field(ge=0)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    allocation_method: Literal["proportional", "quantity"] = "proportional"
    item_costs: dict[str, Decimal] = Field(min_length=1)
    delivery_days: int | None = Field(default=None, ge=0, le=3650)
    payment_type: Literal["cash", "installments", "entry"] = "cash"
    installment_count: int = Field(default=1, ge=1, le=36)
    first_due_days: int = Field(default=30, ge=0, le=3650)
    interval_days: int = Field(default=30, ge=1, le=3650)
    payment_terms: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("item_costs")
    @classmethod
    def validate_item_costs(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        if any(cost < 0 for cost in value.values()):
            raise ValueError("O custo cotado não pode ser negativo")
        return value


class PurchaseItemOut(ORMModel):
    id: str
    product_id: str | None
    sku: str
    description: str
    unit: str = "un"
    quantity: Decimal
    received_quantity: Decimal
    returned_quantity: Decimal = Decimal("0")
    base_unit_cost: Decimal | None = None
    unit_cost: Decimal | None = None
    freight_amount: Decimal | None = Decimal("0")
    tax_amount: Decimal | None = Decimal("0")
    discount_amount: Decimal | None = Decimal("0")
    discount_percent: Decimal | None = Decimal("0")


class PurchaseQuoteOut(ORMModel):
    id: str
    supplier_name: str
    supplier_contact: str | None
    total: Decimal | None = None
    freight_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    allocation_method: str = "proportional"
    item_costs: dict[str, Decimal] | None = None
    delivery_days: int | None
    payment_type: str | None = "cash"
    installment_count: int | None = 1
    first_due_days: int | None = 30
    interval_days: int | None = 30
    payment_terms: str | None
    notes: str | None
    created_at: datetime
