from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VehicleMarketRecord, VehicleMarketSnapshot


def records(
    db: Session,
    snapshot: VehicleMarketSnapshot | None,
    *,
    nationality: str | None,
    brand: str | None,
    model: str | None,
    category: str | None,
    region: str | None,
    age_band: str | None,
) -> list[VehicleMarketRecord]:
    if not snapshot:
        return []
    rows = list(
        db.scalars(
            select(VehicleMarketRecord).where(VehicleMarketRecord.snapshot_id == snapshot.id)
        )
    )
    filters = {
        "nationality": nationality,
        "brand": brand,
        "model": model,
        "vehicle_category": category,
        "region": region,
        "age_band": age_band,
    }
    return [
        row
        for row in rows
        if all(
            not value
            or str(getattr(row, field) or "").casefold() == value.casefold()
            for field, value in filters.items()
        )
    ]


def rank(rows: list[VehicleMarketRecord], field: str) -> list[dict[str, Any]]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        label = str(getattr(row, field) or "Não informado")
        totals[label] += row.value
    total = sum(totals.values())
    return [
        {
            "label": label,
            "value": value,
            "share_pct": round(value / total * 100, 2) if total else None,
        }
        for label, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]


def latest_snapshot(db: Session, metric: str) -> VehicleMarketSnapshot | None:
    return db.scalar(
        select(VehicleMarketSnapshot)
        .where(VehicleMarketSnapshot.metric == metric)
        .order_by(VehicleMarketSnapshot.period.desc())
        .limit(1)
    )
