from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import VehicleMarketRecord, VehicleMarketSnapshot
from app.schemas.vehicle_market import VehicleMarketImportIn
from app.services.vehicle_market_brands import BRAND_NATIONALITIES
from app.services.vehicle_market_queries import latest_snapshot, rank, records


def nationality_for_brand(brand: str | None) -> str | None:
    if not brand:
        return None
    folded = brand.strip().casefold()
    for name, nationality in BRAND_NATIONALITIES.items():
        if name.casefold() == folded:
            return nationality
    return None


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.isoformat()


def _fingerprint(payload: VehicleMarketImportIn) -> str:
    normalized = {
        "source": payload.source,
        "metric": payload.metric,
        "period": payload.period,
        "source_url": payload.source_url,
        "records": [
            row.model_dump(mode="json")
            for row in sorted(
                payload.records,
                key=lambda item: (
                    item.brand.casefold(),
                    (item.model or "").casefold(),
                    item.year_model or 0,
                    item.age_band or "",
                ),
            )
        ],
    }
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _record_key(
    source: str,
    metric: str,
    period: str,
    nationality: str,
    brand: str,
    model: str | None,
    category: str,
    year_model: int | None,
    age_band: str | None,
    region: str | None,
) -> str:
    value = "|".join(
        [
            source,
            metric,
            period,
            nationality,
            brand,
            model or "",
            category,
            str(year_model or ""),
            age_band or "",
            region or "",
        ]
    )
    return hashlib.sha256(value.casefold().encode()).hexdigest()


def import_snapshot(
    db: Session, payload: VehicleMarketImportIn, *, allow_partial: bool = False
) -> VehicleMarketSnapshot:
    fingerprint = _fingerprint(payload)
    current = db.scalar(
        select(VehicleMarketSnapshot).where(
            VehicleMarketSnapshot.source == payload.source,
            VehicleMarketSnapshot.metric == payload.metric,
            VehicleMarketSnapshot.period == payload.period,
        )
    )
    if current and current.validation.get("fingerprint") == fingerprint:
        return current
    rows: list[VehicleMarketRecord] = []
    keys: set[str] = set()
    for row in payload.records:
        nationality = row.nationality or nationality_for_brand(row.brand)
        if not nationality:
            raise ValueError(f"Nacionalidade ausente para a marca {row.brand}.")
        key = _record_key(
            payload.source,
            payload.metric,
            payload.period,
            nationality,
            row.brand,
            row.model,
            row.vehicle_category,
            row.year_model,
            row.age_band,
            row.region,
        )
        if key in keys:
            raise ValueError("O arquivo contém linhas duplicadas para a mesma dimensão.")
        keys.add(key)
        rows.append(
            VehicleMarketRecord(
                id=str(uuid4()),
                snapshot_id="pending",
                record_key=key,
                nationality=nationality,
                brand=row.brand.strip(),
                model=row.model,
                vehicle_category=row.vehicle_category,
                year_model=row.year_model,
                age_band=row.age_band,
                value=row.value,
                region=row.region,
                source_row_label=row.source_row_label,
            )
        )
    if not rows:
        raise ValueError("A publicação não contém registros.")
    previous = db.scalar(
        select(VehicleMarketSnapshot)
        .where(
            VehicleMarketSnapshot.source == payload.source,
            VehicleMarketSnapshot.metric == payload.metric,
            VehicleMarketSnapshot.period < payload.period,
        )
        .order_by(VehicleMarketSnapshot.period.desc())
        .limit(1)
    )
    total = sum(row.value for row in rows)
    if previous and previous.record_count and not allow_partial:
        previous_records = db.scalars(
            select(VehicleMarketRecord).where(
                VehicleMarketRecord.snapshot_id == previous.id
            )
        ).all()
        previous_total = sum(row.value for row in previous_records)
        if previous_total and (total > previous_total * 5 or total < previous_total * 0.2):
            raise ValueError("O total varia de forma anômala em relação à publicação anterior.")
    if current:
        db.execute(delete(VehicleMarketRecord).where(VehicleMarketRecord.snapshot_id == current.id))
        db.delete(current)
        db.flush()
    snapshot = VehicleMarketSnapshot(
        id=str(uuid4()),
        source=payload.source.strip(),
        metric=payload.metric,
        period=payload.period,
        source_url=payload.source_url,
        record_count=len(rows),
        published_at=payload.published_at,
        validation={"fingerprint": fingerprint, "total": total},
    )
    db.add(snapshot)
    db.flush()
    for row in rows:
        row.snapshot_id = snapshot.id
        db.add(row)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def vehicle_market_overview(
    db: Session,
    *,
    period: str | None = None,
    nationality: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    category: str | None = None,
    region: str | None = None,
    age_band: str | None = None,
) -> dict[str, Any]:
    registrations = latest_snapshot(db, "registrations")
    if period:
        registrations = db.scalar(
            select(VehicleMarketSnapshot).where(
                VehicleMarketSnapshot.metric == "registrations",
                VehicleMarketSnapshot.period == period,
            )
        )
    fleet = latest_snapshot(db, "fleet")
    monthly_rows = records(
        db,
        registrations,
        nationality=nationality,
        brand=brand,
        model=model,
        category=category,
        region=region,
        age_band=age_band,
    )
    fleet_rows = records(
        db,
        fleet,
        nationality=nationality,
        brand=brand,
        model=model,
        category=category,
        region=region,
        age_band=age_band,
    )
    ytd_rows: list[VehicleMarketRecord] = []
    trends = []
    monthly_comparisons: dict[str, Any] = {"previous_period": None, "year_ago": None}
    if registrations:
        available = sorted(
            snapshot
            for snapshot in db.scalars(
                select(VehicleMarketSnapshot).where(
                    VehicleMarketSnapshot.metric == "registrations",
                    VehicleMarketSnapshot.period <= registrations.period,
                )
            )
            if snapshot.period
        )
        periods = [
            snapshot.period
            for snapshot in available
            if snapshot.period.startswith(registrations.period[:4])
        ]
        for source_period in periods:
            snapshot = db.scalar(
                select(VehicleMarketSnapshot).where(
                    VehicleMarketSnapshot.metric == "registrations",
                    VehicleMarketSnapshot.period == source_period,
                )
            )
            rows = records(
                db,
                snapshot,
                nationality=nationality,
                brand=brand,
                model=model,
                category=category,
                region=region,
                age_band=age_band,
            )
            ytd_rows.extend(rows)
        trend_snapshots = available[-13:]
        for snapshot in trend_snapshots:
            rows = records(
                db,
                snapshot,
                nationality=nationality,
                brand=brand,
                model=model,
                category=category,
                region=region,
                age_band=age_band,
            )
            trends.append({"period": snapshot.period, "value": sum(row.value for row in rows)})
        previous = next(
            (snapshot for snapshot in reversed(available[:-1])),
            None,
        )
        year_ago_period = f"{int(registrations.period[:4]) - 1}{registrations.period[4:]}"
        year_ago = next(
            (snapshot for snapshot in available if snapshot.period == year_ago_period),
            None,
        )
        monthly_comparisons = {
            "previous_period": _period_comparison(
                db,
                previous,
                previous.period if previous else None,
                nationality=nationality,
                brand=brand,
                model=model,
                category=category,
                region=region,
                age_band=age_band,
            ),
            "year_ago": _period_comparison(
                db,
                year_ago,
                year_ago.period if year_ago else None,
                nationality=nationality,
                brand=brand,
                model=model,
                category=category,
                region=region,
                age_band=age_band,
            ),
        }
    sources = []
    for metric, snapshot in (("registrations", registrations), ("fleet", fleet)):
        sources.append(
            {
                "available": bool(snapshot),
                "source": snapshot.source if snapshot else None,
                "metric": metric,
                "period": snapshot.period if snapshot else None,
                "source_url": snapshot.source_url if snapshot else None,
                "retrieved_at": _iso_utc(snapshot.retrieved_at) if snapshot else None,
                "published_at": _iso_utc(snapshot.published_at) if snapshot else None,
                "status": "published" if snapshot else "unavailable",
            }
        )
    return {
        "scope": {
            "nationality": nationality,
            "brand": brand,
            "model": model,
            "category": category,
            "region": region,
            "age_band": age_band,
        },
        "monthly": {
            "period": registrations.period if registrations else None,
            "total": sum(row.value for row in monthly_rows) if monthly_rows else None,
            "nationalities": rank(monthly_rows, "nationality"),
            "brands": rank(monthly_rows, "brand"),
            "models": rank(monthly_rows, "model"),
        },
        "ytd": {
            "period": registrations.period if registrations else None,
            "total": sum(row.value for row in ytd_rows) if ytd_rows else None,
            "nationalities": rank(ytd_rows, "nationality"),
            "brands": rank(ytd_rows, "brand"),
            "models": rank(ytd_rows, "model"),
        },
        "trend": trends[-13:],
        "comparisons": monthly_comparisons,
        "fleet": {
            "period": fleet.period if fleet else None,
            "total": sum(row.value for row in fleet_rows) if fleet_rows else None,
            "nationalities": rank(fleet_rows, "nationality"),
            "brands": rank(fleet_rows, "brand"),
            "models": rank(fleet_rows, "model"),
            "age_bands": rank(fleet_rows, "age_band"),
        },
        "sources": sources,
        "brand_nationalities": BRAND_NATIONALITIES,
        "definitions": {
            "registrations": (
                "Emplacamentos aproximam vendas de veículos novos, não entregas finais."
            ),
            "fleet": "Frota registrada é um estoque e não comprova uso diário.",
        },
    }


def _period_comparison(
    db: Session,
    snapshot: VehicleMarketSnapshot | None,
    period: str | None,
    **filters: Any,
) -> dict[str, Any] | None:
    if not snapshot:
        return None
    rows = records(db, snapshot, **filters)
    return {"period": period, "total": sum(row.value for row in rows)}
