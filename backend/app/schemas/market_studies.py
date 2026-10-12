from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from app.schemas.base import ORMModel


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
