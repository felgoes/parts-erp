from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import VehicleMarketRecord, VehicleMarketSnapshot
from app.services.vehicle_market_live import SOURCE, SOURCE_URL

router = APIRouter(prefix="/catalog", tags=["Catalogo publico"])
Category = Literal["automovel", "comercial_leve"]


class RegistrationRank(BaseModel):
    model: str
    registrations: int


class PublicRanking(BaseModel):
    period: str | None = None
    source: str = SOURCE
    source_url: str = SOURCE_URL
    items: list[RegistrationRank]


@router.get("/vehicle-ranking", response_model=PublicRanking)
def catalog_vehicle_ranking(
    response: Response,
    category: Category = "automovel",
    db: Session = Depends(get_db),
) -> PublicRanking:
    """Read the last cached public publication. Visitors cannot trigger a source refresh."""
    response.headers["Cache-Control"] = "public, max-age=300"
    period = VehicleMarketSnapshot.period
    snapshot = VehicleMarketSnapshot
    record = VehicleMarketRecord
    latest = db.scalar(
        select(snapshot)
        .where(
            snapshot.source == SOURCE,
            snapshot.metric == "registrations",
            select(record.id)
            .where(record.snapshot_id == snapshot.id, record.vehicle_category == category)
            .exists(),
        )
        .order_by(period.desc())
        .limit(1)
    )
    if latest is None:
        return PublicRanking(items=[])

    rows = db.execute(
        select(record.model, record.value)
        .where(
            record.snapshot_id == latest.id,
            record.vehicle_category == category,
            record.model.is_not(None),
        )
        .order_by(record.value.desc(), record.model)
        .limit(20)
    )
    return PublicRanking(
        period=latest.period,
        items=[RegistrationRank(model=model, registrations=value) for model, value in rows],
    )
