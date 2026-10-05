from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import MarketStudy, User
from app.schemas.common import (
    MarketStudyConnectorOut,
    MarketStudyConnectorUpdate,
    MarketStudyCreate,
    MarketStudyOut,
    MarketStudyPurchaseIn,
    PurchaseOut,
)
from app.services.market_research import (
    connector_config,
    connector_output,
    convert_study_to_purchase,
    run_study,
    save_connector,
)

router = APIRouter(prefix="/market-studies", tags=["Estudos de mercado"])


@router.get("/connector", response_model=MarketStudyConnectorOut)
def get_connector(
    db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.STUDY_READ))
) -> dict:
    return connector_output(connector_config(db))


@router.put("/connector", response_model=MarketStudyConnectorOut)
def update_connector(
    payload: MarketStudyConnectorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_CONFIG)),
) -> dict:
    try:
        config = save_connector(db, **payload.model_dump())
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return connector_output(config)


@router.get("", response_model=list[MarketStudyOut])
def list_studies(
    db: Session = Depends(get_db), _: User = Depends(require_permission(Permission.STUDY_READ))
) -> list[MarketStudy]:
    return list(db.scalars(select(MarketStudy).order_by(MarketStudy.created_at.desc()).limit(100)))


@router.post("", response_model=MarketStudyOut, status_code=201)
def create_study(
    payload: MarketStudyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.STUDY_RUN)),
) -> MarketStudy:
    try:
        return run_study(db, user, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{study_id}/purchase", response_model=PurchaseOut, status_code=201)
def create_purchase_draft(
    study_id: str,
    payload: MarketStudyPurchaseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.PURCHASE_MANAGE)),
):
    study = db.scalar(select(MarketStudy).where(MarketStudy.id == study_id).with_for_update())
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado")
    purchase = convert_study_to_purchase(
        db, study, user, sku=payload.sku.strip(), quantity=Decimal(payload.quantity)
    )
    return purchase
