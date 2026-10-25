from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import VehicleCatalogCache
from app.services.vehicle_market import nationality_for_brand

CATALOG_TTL = timedelta(hours=24)


def _cached(db: Session, kind: str, key: str) -> VehicleCatalogCache | None:
    return db.scalar(
        select(VehicleCatalogCache).where(
            VehicleCatalogCache.kind == kind,
            VehicleCatalogCache.cache_key == key,
        )
    )


def _is_fresh(entry: VehicleCatalogCache) -> bool:
    retrieved = (
        entry.retrieved_at
        if entry.retrieved_at.tzinfo
        else entry.retrieved_at.replace(tzinfo=UTC)
    )
    return retrieved >= datetime.now(UTC) - CATALOG_TTL


def _fetch(path: str, params: dict[str, str] | None = None) -> list[str]:
    settings = get_settings()
    headers = {}
    if settings.fipe_market_api_key:
        headers["X-API-Key"] = settings.fipe_market_api_key.get_secret_value()
    try:
        response = httpx.get(
            f"{str(settings.fipe_market_catalog_url).rstrip('/')}{path}",
            params=params,
            headers=headers,
            timeout=20.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("O catálogo automotivo está indisponível.") from exc
    if not isinstance(payload, list):
        raise RuntimeError("O catálogo automotivo retornou formato inválido.")
    values = []
    for item in payload:
        value = item.get("name") if isinstance(item, dict) else item
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    if not values:
        raise RuntimeError("O catálogo automotivo retornou vazio.")
    return sorted(set(values), key=str.casefold)


def _load(
    db: Session,
    kind: str,
    key: str,
    path: str,
    params: dict[str, str] | None = None,
) -> dict:
    entry = _cached(db, kind, key)
    if entry and _is_fresh(entry):
        return {
            "data": entry.data,
            "status": "cached",
            "retrieved_at": entry.retrieved_at,
        }
    try:
        values = _fetch(path, params)
        if entry is None:
            entry = VehicleCatalogCache(
                id=str(uuid4()),
                kind=kind,
                cache_key=key,
                data=values,
            )
            db.add(entry)
        else:
            entry.data = values
            entry.retrieved_at = datetime.now(UTC)
        db.commit()
        db.refresh(entry)
        return {
            "data": entry.data,
            "status": "updated",
            "retrieved_at": entry.retrieved_at,
        }
    except RuntimeError:
        db.rollback()
        if entry:
            return {
                "data": entry.data,
                "status": "stale",
                "retrieved_at": entry.retrieved_at,
            }
        return {"data": [], "status": "unavailable", "retrieved_at": None}


def complete_brands(db: Session) -> dict:
    return _load(db, "brands", "cars", "/marcas", {"tipo_veiculo": "1"})


def brand_models(db: Session, brand: str) -> dict:
    catalog = complete_brands(db)
    brands = catalog["data"]
    match = next((item for item in brands if item.casefold() == brand.strip().casefold()), None)
    if not match:
        if catalog["status"] == "unavailable" and nationality_for_brand(brand):
            return {
                "brand": brand,
                "found": True,
                "models": [],
                "status": "unavailable",
                "retrieved_at": None,
            }
        return {
            "brand": brand,
            "found": False,
            "models": [],
            "status": "not_found",
            "retrieved_at": None,
        }
    loaded = _load(
        db,
        "models",
        match.casefold(),
        "/modelos",
        {"tipo_veiculo": "1", "marca": match},
    )
    return {
        "brand": match,
        "found": True,
        "models": loaded["data"],
        "status": loaded["status"],
        "retrieved_at": loaded["retrieved_at"],
    }


def model_families(models: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, int] = {}
    for model in models:
        family = model.split(" ", 1)[0].strip()
        grouped[family] = grouped.get(family, 0) + 1
    return [
        {"name": name, "versions": count}
        for name, count in sorted(grouped.items(), key=lambda item: item[0].casefold())
    ]
