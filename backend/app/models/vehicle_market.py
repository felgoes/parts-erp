from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import now_utc


class VehicleMarketSnapshot(Base):
    """Validated source publication; records are promoted atomically by period."""

    __tablename__ = "vehicle_market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "source", "metric", "period", name="uq_vehicle_market_source_metric_period"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    validation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class VehicleMarketRecord(Base):
    __tablename__ = "vehicle_market_records"
    __table_args__ = (UniqueConstraint("record_key", name="uq_vehicle_market_record_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    record_key: Mapped[str] = mapped_column(String(64), nullable=False)
    nationality: Mapped[str] = mapped_column(String(80), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str | None] = mapped_column(String(160))
    vehicle_category: Mapped[str] = mapped_column(String(60), default="automovel")
    year_model: Mapped[int | None] = mapped_column(Integer)
    age_band: Mapped[str | None] = mapped_column(String(40))
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    region: Mapped[str | None] = mapped_column(String(80))
    source_row_label: Mapped[str | None] = mapped_column(Text)


class VehicleCatalogCache(Base):
    """Short-lived cache for the complete FIPE brand/model directory."""

    __tablename__ = "vehicle_catalog_cache"
    __table_args__ = (
        UniqueConstraint("kind", "cache_key", name="uq_vehicle_catalog_cache_kind_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(160), nullable=False)
    data: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class VehicleFleetImportRun(Base):
    """Durable status for the large monthly RENAVAM import."""

    __tablename__ = "vehicle_fleet_import_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    source_rows: Mapped[int | None] = mapped_column(Integer)
    aggregate_count: Mapped[int | None] = mapped_column(Integer)
    total_vehicles: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
