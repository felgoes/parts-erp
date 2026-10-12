from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    Field,
)

from app.schemas.base import ORMModel


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
