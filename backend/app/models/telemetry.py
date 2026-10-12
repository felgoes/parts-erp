"""Eventos de telemetria e histórico de saúde, separados do arquivo principal de modelos."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import new_id, now_utc


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (Index("ix_telemetry_events_name_created", "name", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), index=True)
    source: Mapped[str] = mapped_column(String(30), default="site")
    visitor_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class HealthSnapshot(Base):
    __tablename__ = "health_snapshots"
    __table_args__ = (Index("ix_health_snapshots_checked_at", "checked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    check_name: Mapped[str] = mapped_column(String(60), index=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    detail: Mapped[str | None] = mapped_column(String(255))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
