from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import VehicleMarketSnapshot
from app.schemas.vehicle_market import VehicleMarketImportIn, VehicleMarketRecordIn
from app.services.vehicle_market import import_snapshot, nationality_for_brand
from app.services.vehicle_market_models import brand_for_model

SOURCE = "FENABRAVE via FIPE API BRASIL"
SOURCE_URL = "https://fipeapibrasil.com.br/docs"
_sync_lock = Lock()


class VehicleMarketSourceError(RuntimeError):
    pass


def _fetch_live_payload() -> dict[str, Any]:
    settings = get_settings()
    headers = {}
    if settings.fipe_market_api_key:
        headers["X-API-Key"] = settings.fipe_market_api_key.get_secret_value()
    try:
        response = httpx.get(
            str(settings.fipe_market_api_url),
            headers=headers,
            timeout=20.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        raise VehicleMarketSourceError("A fonte de emplacamentos está indisponível.") from exc
    if not response.is_success:
        raise VehicleMarketSourceError(
            f"A fonte de emplacamentos respondeu HTTP {response.status_code}."
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise VehicleMarketSourceError(
            "A fonte de emplacamentos retornou conteúdo inválido."
        ) from exc
    if not isinstance(payload, dict) or not payload.get("sucesso"):
        raise VehicleMarketSourceError("A fonte de emplacamentos não confirmou a consulta.")
    if not isinstance(payload.get("segmentos"), dict):
        raise VehicleMarketSourceError("A fonte não retornou os segmentos esperados.")
    return payload


def _latest_snapshot(db: Session) -> VehicleMarketSnapshot | None:
    return db.scalar(
        select(VehicleMarketSnapshot)
        .where(
            VehicleMarketSnapshot.source == SOURCE,
            VehicleMarketSnapshot.metric == "registrations",
        )
        .order_by(VehicleMarketSnapshot.period.desc())
        .limit(1)
    )


def _iso_utc(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def _to_import(payload: dict[str, Any]) -> VehicleMarketImportIn:
    year = int(payload.get("ano") or 0)
    month = int(payload.get("mes") or 0)
    if year < 2000 or not 1 <= month <= 12:
        raise VehicleMarketSourceError("A competência da fonte está inválida.")
    segments = payload["segmentos"]
    records: list[VehicleMarketRecordIn] = []
    for key, category in (("auto", "automovel"), ("comercial", "comercial_leve")):
        segment = segments.get(key)
        if not isinstance(segment, dict):
            continue
        for item in segment.get("itens", []):
            if not isinstance(item, dict):
                continue
            model = " ".join(str(item.get("modelo") or "").split())
            units = item.get("unidades")
            if not model or not isinstance(units, int) or units < 0:
                continue
            brand = brand_for_model(model)
            records.append(
                VehicleMarketRecordIn(
                    nationality=nationality_for_brand(brand) or "Não informada",
                    brand=brand,
                    model=model,
                    vehicle_category=category,
                    value=units,
                    source_row_label=model,
                )
            )
    if not records:
        raise VehicleMarketSourceError("A fonte não retornou veículos válidos.")
    return VehicleMarketImportIn(
        source=SOURCE,
        metric="registrations",
        period=f"{year:04d}-{month:02d}",
        source_url=SOURCE_URL,
        records=records,
    )


def sync_live_vehicle_market(
    db: Session, *, force: bool = False
) -> dict[str, Any]:
    settings = get_settings()
    latest = _latest_snapshot(db)
    ttl = timedelta(hours=settings.vehicle_market_cache_hours)
    retrieved_at = latest.retrieved_at if latest else None
    if retrieved_at and retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=UTC)
    if latest and retrieved_at and not force and retrieved_at >= datetime.now(UTC) - ttl:
        return {
            "status": "cached",
            "period": latest.period,
            "retrieved_at": retrieved_at.isoformat(),
        }
    if not _sync_lock.acquire(blocking=False):
        return {
            "status": "updating",
            "period": latest.period if latest else None,
            "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
        }
    try:
        payload = _fetch_live_payload()
        snapshot = import_snapshot(db, _to_import(payload), allow_partial=True)
        snapshot.validation = {
            **snapshot.validation,
            "status": "partial",
            "reference": payload.get("referencia"),
            "ranking_scope": "Top 20 por segmento",
        }
        db.commit()
        return {
            "status": "updated",
            "period": snapshot.period,
            "retrieved_at": _iso_utc(snapshot.retrieved_at),
        }
    except (VehicleMarketSourceError, ValueError, httpx.HTTPError) as exc:
        db.rollback()
        return {
            "status": "unavailable",
            "period": latest.period if latest else None,
            "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
            "message": str(exc),
        }
    finally:
        _sync_lock.release()
