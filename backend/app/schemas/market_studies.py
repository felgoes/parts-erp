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
    mode: Literal["legacy", "brand", "nationality"] = "legacy"
    brand: str | None = Field(default=None, max_length=120)
    nationality: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    vehicle_categories: list[str] = Field(default_factory=list, max_length=10)
    include_suppliers_china: bool = False
    include_competitor_links: bool = True
    search_term: str | None = Field(default=None, max_length=200)
    sku: str | None = Field(default=None, max_length=80)
    category_id: str | None = Field(default=None, max_length=40)
    landed_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    target_margin_pct: Decimal = Field(
        default=Decimal("25"), ge=0, lt=80, max_digits=5, decimal_places=2
    )
    marketplace_fee_pct: Decimal | None = Field(
        default=None, ge=0, lt=80, max_digits=5, decimal_places=2
    )
    shipping_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    fixed_fee: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    outbound_shipping: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    oem: str | None = Field(default=None, max_length=120)
    application: str | None = Field(default=None, max_length=300)
    fitments: list[dict[str, Any]] = Field(default_factory=list, max_length=20)

    @field_validator("search_term")
    @classmethod
    def trim_search_term(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        if not normalized:
            return None
        return normalized

    @model_validator(mode="after")
    def validate_price_scenario(self) -> "MarketStudyCreate":
        if self.mode == "legacy" and not self.search_term:
            raise ValueError("Informe o nome ou código da peça")
        if self.mode == "brand" and not (self.brand or "").strip():
            raise ValueError("Escolha uma marca")
        if self.mode == "nationality" and not (self.nationality or "").strip():
            raise ValueError("Escolha uma nacionalidade")
        if (
            self.marketplace_fee_pct is not None
            and self.target_margin_pct + self.marketplace_fee_pct >= 100
        ):
            raise ValueError("Taxa do canal e margem desejada precisam somar menos de 100%")
        return self

    def study_label(self) -> str:
        if self.mode == "brand":
            return (self.brand or "").strip()
        if self.mode == "nationality":
            return (self.nationality or "").strip()
        return self.search_term or "Estudo de mercado"


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


class MarketStudySummaryOut(BaseModel):
    id: str
    mode: str
    selection: str
    nationality: str | None
    brand: str | None
    conclusion: str
    best_candidate: str | None
    decision: str | None
    score: int | None
    confidence: str | None
    estimated_margin_pct: Decimal | None
    status: str
    created_at: datetime


class MarketStudyListOut(BaseModel):
    total: int
    items: list[MarketStudySummaryOut]


class MarketStudyPurchaseIn(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
