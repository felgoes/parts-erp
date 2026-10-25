from __future__ import annotations

from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    VehicleFleetImportRun,
    VehicleMarketRecord,
    VehicleMarketSnapshot,
)

AGE_ORDER = {
    "0 a 5 anos": 0,
    "6 a 10 anos": 1,
    "11 a 15 anos": 2,
    "16 a 20 anos": 3,
    "21 anos ou mais": 4,
    "Não informado": 5,
}


def _conditions(
    snapshot_id: str,
    *,
    brand: str | None = None,
    nationality: str | None = None,
    model: str | None = None,
    age_band: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list:
    conditions: list = [VehicleMarketRecord.snapshot_id == snapshot_id]
    if brand:
        conditions.append(func.lower(VehicleMarketRecord.brand) == brand.strip().casefold())
    if nationality:
        conditions.append(
            func.lower(VehicleMarketRecord.nationality) == nationality.strip().casefold()
        )
    if model:
        conditions.append(VehicleMarketRecord.model.ilike(f"%{model.strip()}%"))
    if age_band:
        conditions.append(VehicleMarketRecord.age_band == age_band)
    if year_from is not None:
        conditions.append(VehicleMarketRecord.year_model >= year_from)
    if year_to is not None:
        conditions.append(VehicleMarketRecord.year_model <= year_to)
    return conditions


def _total(db: Session, snapshot_id: str, conditions: list) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(VehicleMarketRecord.value), 0)).where(
                *conditions
            )
        )
        or 0
    )


def _share(value: int, total: int) -> float | None:
    return round(value / total * 100, 2) if total else None


def _rank(
    db: Session,
    column,
    conditions: list,
    total: int,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    value = func.sum(VehicleMarketRecord.value).label("value")
    rows = db.execute(
        select(column.label("label"), value)
        .where(*conditions)
        .group_by(column)
        .order_by(value.desc(), column)
        .limit(limit)
    ).all()
    return [
        {
            "label": str(label or "Não informado"),
            "value": int(amount),
            "share_pct": _share(int(amount), total),
        }
        for label, amount in rows
    ]


def _selected_snapshot(db: Session, period: str | None) -> VehicleMarketSnapshot | None:
    statement = select(VehicleMarketSnapshot).where(
        VehicleMarketSnapshot.metric == "fleet"
    )
    if period:
        statement = statement.where(VehicleMarketSnapshot.period == period)
    return db.scalar(statement.order_by(VehicleMarketSnapshot.period.desc()).limit(1))


def fleet_overview(
    db: Session,
    *,
    period: str | None = None,
    brand: str | None = None,
    nationality: str | None = None,
    model: str | None = None,
    age_band: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> dict[str, Any]:
    snapshot = _selected_snapshot(db, period)
    available = list(
        db.scalars(
            select(VehicleMarketSnapshot)
            .where(VehicleMarketSnapshot.metric == "fleet")
            .order_by(VehicleMarketSnapshot.period.desc())
        )
    )
    if not snapshot:
        return {
            "available": False,
            "periods": [row.period for row in available],
            "message": "A frota oficial ainda não foi importada.",
        }
    conditions = _conditions(
        snapshot.id,
        brand=brand,
        nationality=nationality,
        model=model,
        age_band=age_band,
        year_from=year_from,
        year_to=year_to,
    )
    total = _total(db, snapshot.id, conditions)
    brand_count = int(
        db.scalar(
            select(func.count(func.distinct(VehicleMarketRecord.brand))).where(
                *conditions
            )
        )
        or 0
    )
    model_count = int(
        db.scalar(
            select(
                func.count(
                    func.distinct(
                        VehicleMarketRecord.brand + "|" + VehicleMarketRecord.model
                    )
                )
            ).where(*conditions)
        )
        or 0
    )
    previous_snapshot = next(
        (row for row in available if row.period < snapshot.period),
        None,
    )
    previous_total = None
    if previous_snapshot:
        previous_conditions = _conditions(
            previous_snapshot.id,
            brand=brand,
            nationality=nationality,
            model=model,
            age_band=age_band,
            year_from=year_from,
            year_to=year_to,
        )
        previous_total = _total(db, previous_snapshot.id, previous_conditions)
    change_pct = (
        round((total - previous_total) / previous_total * 100, 2)
        if previous_total
        else None
    )
    all_conditions = [VehicleMarketRecord.snapshot_id == snapshot.id]
    age_rows = _rank(
        db, VehicleMarketRecord.age_band, conditions, total, limit=10
    )
    age_rows.sort(key=lambda row: AGE_ORDER.get(row["label"], 99))
    latest_run = db.scalar(
        select(VehicleFleetImportRun)
        .order_by(VehicleFleetImportRun.started_at.desc())
        .limit(1)
    )
    return {
        "available": True,
        "period": snapshot.period,
        "collected_at": (
            snapshot.retrieved_at
            if snapshot.retrieved_at.tzinfo
            else snapshot.retrieved_at.replace(tzinfo=UTC)
        ).isoformat(),
        "source": snapshot.source,
        "source_url": snapshot.source_url,
        "periods": [row.period for row in available],
        "total": total,
        "previous_period": previous_snapshot.period if previous_snapshot else None,
        "previous_total": previous_total,
        "change_pct": change_pct,
        "brand_count": brand_count,
        "model_count": model_count,
        "brands": _rank(db, VehicleMarketRecord.brand, conditions, total, limit=15),
        "nationalities": _rank(
            db, VehicleMarketRecord.nationality, conditions, total, limit=15
        ),
        "models": [
            {
                "brand": row.brand,
                "model": row.model,
                "value": int(row.value),
                "share_pct": _share(int(row.value), total),
            }
            for row in db.execute(
                select(
                    VehicleMarketRecord.brand,
                    VehicleMarketRecord.model,
                    func.sum(VehicleMarketRecord.value).label("value"),
                )
                .where(*conditions)
                .group_by(VehicleMarketRecord.brand, VehicleMarketRecord.model)
                .order_by(func.sum(VehicleMarketRecord.value).desc())
                .limit(15)
            ).all()
        ],
        "age_bands": age_rows,
        "years": [
            {"label": str(year), "value": int(value), "share_pct": _share(int(value), total)}
            for year, value in db.execute(
                select(
                    VehicleMarketRecord.year_model,
                    func.sum(VehicleMarketRecord.value),
                )
                .where(*conditions, VehicleMarketRecord.year_model.is_not(None))
                .group_by(VehicleMarketRecord.year_model)
                .order_by(VehicleMarketRecord.year_model)
            ).all()
        ],
        "filters": {
            "brands": list(
                db.scalars(
                    select(VehicleMarketRecord.brand)
                    .where(*all_conditions)
                    .distinct()
                    .order_by(VehicleMarketRecord.brand)
                )
            ),
            "nationalities": list(
                db.scalars(
                    select(VehicleMarketRecord.nationality)
                    .where(*all_conditions)
                    .distinct()
                    .order_by(VehicleMarketRecord.nationality)
                )
            ),
            "age_bands": list(AGE_ORDER),
        },
        "import_status": {
            "status": latest_run.status if latest_run else "not_started",
            "period": latest_run.period if latest_run else None,
            "source_rows": latest_run.source_rows if latest_run else None,
            "aggregate_count": latest_run.aggregate_count if latest_run else None,
            "error": latest_run.error if latest_run else None,
        },
    }


def fleet_records(
    db: Session,
    *,
    page: int,
    page_size: int,
    period: str | None = None,
    brand: str | None = None,
    nationality: str | None = None,
    model: str | None = None,
    age_band: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    sort: str = "fleet_desc",
) -> dict[str, Any]:
    snapshot = _selected_snapshot(db, period)
    if not snapshot:
        return {"total": 0, "page": page, "page_size": page_size, "items": []}
    conditions = _conditions(
        snapshot.id,
        brand=brand,
        nationality=nationality,
        model=model,
        age_band=age_band,
        year_from=year_from,
        year_to=year_to,
    )
    grouped = (
        select(
            VehicleMarketRecord.brand,
            VehicleMarketRecord.model,
            VehicleMarketRecord.year_model,
            VehicleMarketRecord.age_band,
            func.sum(VehicleMarketRecord.value).label("value"),
        )
        .where(*conditions)
        .group_by(
            VehicleMarketRecord.brand,
            VehicleMarketRecord.model,
            VehicleMarketRecord.year_model,
            VehicleMarketRecord.age_band,
        )
    )
    total = int(
        db.scalar(select(func.count()).select_from(grouped.subquery())) or 0
    )
    order = (
        (func.sum(VehicleMarketRecord.value).asc(), VehicleMarketRecord.model)
        if sort == "fleet_asc"
        else (func.sum(VehicleMarketRecord.value).desc(), VehicleMarketRecord.model)
    )
    rows = db.execute(
        grouped.order_by(*order).offset((page - 1) * page_size).limit(page_size)
    ).all()
    period_total = _total(db, snapshot.id, conditions)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "period": snapshot.period,
        "items": [
            {
                "brand": row.brand,
                "model": row.model,
                "year": row.year_model,
                "age_band": row.age_band,
                "value": int(row.value),
                "share_pct": _share(int(row.value), period_total),
            }
            for row in rows
        ],
    }
