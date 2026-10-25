from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import User
from app.services.fleet_analytics import fleet_overview, fleet_records

router = APIRouter(prefix="/fleet", tags=["Frota do Brasil"])


@router.get("/overview")
def overview(
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    category: str = Query(default="cars", pattern="^(cars|motorcycles)$"),
    brand: str | None = None,
    nationality: str | None = None,
    model: str | None = None,
    age_band: str | None = None,
    year_from: int | None = Query(default=None, ge=1900, le=2100),
    year_to: int | None = Query(default=None, ge=1900, le=2100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_READ)),
) -> dict:
    return fleet_overview(
        db,
        period=period,
        category=category,
        brand=brand,
        nationality=nationality,
        model=model,
        age_band=age_band,
        year_from=year_from,
        year_to=year_to,
    )


@router.get("/records")
def records(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    category: str = Query(default="cars", pattern="^(cars|motorcycles)$"),
    brand: str | None = None,
    nationality: str | None = None,
    model: str | None = None,
    age_band: str | None = None,
    year_from: int | None = Query(default=None, ge=1900, le=2100),
    year_to: int | None = Query(default=None, ge=1900, le=2100),
    sort: str = Query(default="fleet_desc", pattern="^(fleet_desc|fleet_asc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_READ)),
) -> dict:
    return fleet_records(
        db,
        page=page,
        page_size=page_size,
        period=period,
        category=category,
        brand=brand,
        nationality=nationality,
        model=model,
        age_band=age_band,
        year_from=year_from,
        year_to=year_to,
        sort=sort,
    )
