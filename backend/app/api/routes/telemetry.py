from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import HealthSnapshot, TelemetryEvent, User
from app.schemas.common import (
    EventCount,
    TelemetryEventCreate,
    TelemetryHealthOut,
    TelemetrySummary,
)

router = APIRouter(prefix="/telemetry", tags=["Monitoramento"])

ALLOWED_EVENTS = {
    "landing_view",
    "catalog_search",
    "product_view",
    "mercado_livre_click",
    "whatsapp_click",
    "catalog_empty_result",
}
ALLOWED_PROPERTIES = {"sku", "placement", "brand", "model", "year", "source", "campaign"}
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _safe_properties(properties: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in properties.items():
        if key not in ALLOWED_PROPERTIES:
            continue
        if isinstance(value, (str, int, float, bool)) and len(str(value)) <= 120:
            clean[key] = value
    return clean


def _enforce_rate_limit(key: str, limit: int) -> None:
    now = monotonic()
    with _rate_lock:
        window = _rate_windows[key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(
                status_code=429, detail="Muitos eventos; tente novamente em instantes"
            )
        window.append(now)


@router.post("/events", status_code=202)
def collect_event(
    payload: TelemetryEventCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if payload.name not in ALLOWED_EVENTS:
        raise HTTPException(status_code=422, detail="Evento nao permitido")
    settings = get_settings()
    anonymous_id = payload.anonymous_id or ""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    client_ip = (forwarded or (request.client.host if request.client else "unknown")).split(",")[0]
    _enforce_rate_limit(
        sha256(f"{client_ip}:{anonymous_id}".encode()).hexdigest(),
        settings.telemetry_rate_limit_per_minute,
    )
    visitor_hash = (
        sha256(f"{settings.secret_key.get_secret_value()}:{anonymous_id}".encode()).hexdigest()
        if anonymous_id
        else None
    )
    db.add(
        TelemetryEvent(
            name=payload.name,
            source=payload.source,
            visitor_hash=visitor_hash,
            properties=_safe_properties(payload.properties),
        )
    )
    db.commit()
    return {"status": "accepted"}


@router.get("/summary", response_model=TelemetrySummary)
def summary(
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TelemetrySummary:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(TelemetryEvent.name, func.count(TelemetryEvent.id))
        .where(TelemetryEvent.created_at >= since)
        .group_by(TelemetryEvent.name)
        .order_by(func.count(TelemetryEvent.id).desc())
    ).all()
    counts = [EventCount(name=name, count=count) for name, count in rows]
    health = list(
        db.scalars(select(HealthSnapshot).order_by(HealthSnapshot.checked_at.desc()).limit(20))
    )
    return TelemetrySummary(days=days, events=counts, health=health)


@router.get("/health", response_model=list[TelemetryHealthOut])
def health(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[TelemetryHealthOut]:
    return list(
        db.scalars(select(HealthSnapshot).order_by(HealthSnapshot.checked_at.desc()).limit(50))
    )
