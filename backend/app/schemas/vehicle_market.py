from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class VehicleMarketRecordIn(BaseModel):
    nationality: str | None = Field(default=None, max_length=80)
    brand: str = Field(min_length=1, max_length=120)
    model: str | None = Field(default=None, max_length=160)
    vehicle_category: str = Field(default="automovel", max_length=60)
    year_model: int | None = Field(default=None, ge=1900, le=2100)
    age_band: str | None = Field(default=None, max_length=40)
    value: int = Field(ge=0)
    region: str | None = Field(default=None, max_length=80)
    source_row_label: str | None = Field(default=None, max_length=500)


class VehicleMarketImportIn(BaseModel):
    source: str = Field(min_length=1, max_length=80)
    metric: Literal["registrations", "fleet"]
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    source_url: str = Field(min_length=8, max_length=1000)
    published_at: datetime | None = None
    records: list[VehicleMarketRecordIn] = Field(min_length=1, max_length=100_000)

    @field_validator("source_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Informe a URL HTTPS da fonte")
        return value


class VehicleMarketImportOut(BaseModel):
    snapshot_id: str
    source: str
    metric: str
    period: str
    records: int
    status: Literal["published"]
