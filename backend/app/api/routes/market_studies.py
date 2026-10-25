from datetime import UTC
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import MarketplaceConfig, MarketStudy, User
from app.schemas.common import (
    MarketStudyConnectorOut,
    MarketStudyConnectorUpdate,
    MarketStudyCreate,
    MarketStudyListOut,
    MarketStudyOut,
    MarketStudyPurchaseIn,
    PurchaseOut,
    VehicleMarketImportIn,
    VehicleMarketImportOut,
)
from app.services.company_profile import study_company_parameters
from app.services.market_research import (
    connector_config,
    connector_output,
    convert_study_to_purchase,
    run_study,
    save_connector,
)
from app.services.market_study_opportunity import (
    process_queued_opportunity,
    queue_opportunity_study,
)
from app.services.vehicle_market import import_snapshot, vehicle_market_overview
from app.services.vehicle_market_catalog import (
    brand_models,
    complete_brands,
    model_families,
)
from app.services.vehicle_market_fleet_source import fleet_source_status
from app.services.vehicle_market_live import sync_live_vehicle_market

router = APIRouter(prefix="/market-studies", tags=["Estudos de mercado"])


@router.get("/defaults")
def get_study_defaults(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_RUN)),
) -> dict:
    config = db.scalar(select(MarketplaceConfig).limit(1))
    company, missing = study_company_parameters(db)
    return {
        "marketplace_fee_pct": company.get("channel_commission_pct"),
        "target_margin_pct": company.get("target_margin_pct"),
        "profile_version": company.get("profile_revision"),
        "missing_company_fields": missing,
        "legacy_marketplace_fee_pct": (
            config.study_default_commission_pct if config else Decimal("16")
        ),
    }


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


def _summary(study: MarketStudy) -> dict:
    result = study.result or {}
    scope = result.get("scope") or {}
    best = result.get("best_candidate") or {}
    decision = best.get("decision") or result.get("decision")
    created_at = study.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "id": study.id,
        "mode": scope.get("mode", "legacy"),
        "selection": scope.get("brand")
        or scope.get("nationality")
        or study.search_term,
        "nationality": scope.get("nationality"),
        "brand": scope.get("brand"),
        "conclusion": result.get("executive_summary")
        or (result.get("market_metrics") or {}).get("conclusion")
        or "Sem conclusão",
        "best_candidate": best.get("part_family")
        or best.get("product_name")
        or (result.get("market_metrics") or {}).get("conclusion"),
        "decision": decision,
        "score": best.get("score"),
        "confidence": best.get("confidence")
        or (result.get("market_metrics") or {}).get("sample_confidence"),
        "estimated_margin_pct": (best.get("unit_economics") or {}).get(
            "partial_contribution_margin_pct"
        )
        or (result.get("price_scenario") or {}).get("market_margin_at_median_pct"),
        "status": study.status,
        "created_at": created_at,
    }


@router.get("", response_model=MarketStudyListOut)
def list_studies(
    search: str | None = Query(default=None, max_length=120),
    status: str | None = Query(default=None, max_length=40),
    decision: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_READ)),
) -> dict:
    statement = select(MarketStudy)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(MarketStudy.search_term.ilike(pattern), MarketStudy.sku.ilike(pattern))
        )
    if status:
        statement = statement.where(MarketStudy.status == status)
    rows = list(db.scalars(statement.order_by(MarketStudy.created_at.desc())))
    summaries = [_summary(row) for row in rows]
    if decision:
        summaries = [row for row in summaries if row["decision"] == decision]
    return {"total": len(summaries), "items": summaries[offset : offset + limit]}


@router.get("/vehicle-market")
def read_vehicle_market(
    period: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    nationality: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    category: str | None = None,
    region: str | None = None,
    age_band: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_READ)),
) -> dict:
    sync = sync_live_vehicle_market(db)
    overview = vehicle_market_overview(
        db,
        period=period,
        nationality=nationality,
        brand=brand,
        model=model,
        category=category,
        region=region,
        age_band=age_band,
    )
    overview["live_sync"] = sync
    overview["fleet_publication"] = fleet_source_status()
    brands = complete_brands(db)
    overview["available_brands"] = brands["data"]
    overview["catalog_status"] = brands["status"]
    if brand:
        selected = brand_models(db, brand)
        selected["families"] = model_families(selected["models"])
        selected["in_top_20"] = any(
            row["label"].casefold() == selected["brand"].casefold()
            for row in overview["monthly"]["brands"]
        )
        selected["retrieved_at"] = (
            selected["retrieved_at"].replace(tzinfo=UTC).isoformat()
            if selected["retrieved_at"] and selected["retrieved_at"].tzinfo is None
            else selected["retrieved_at"].isoformat()
            if selected["retrieved_at"]
            else None
        )
        overview["selected_brand"] = selected
    return overview


@router.post("/vehicle-market/import", response_model=VehicleMarketImportOut)
def import_vehicle_market(
    payload: VehicleMarketImportIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_CONFIG)),
) -> dict:
    try:
        snapshot = import_snapshot(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "snapshot_id": snapshot.id,
        "source": snapshot.source,
        "metric": snapshot.metric,
        "period": snapshot.period,
        "records": snapshot.record_count,
        "status": "published",
    }


@router.post("", response_model=MarketStudyOut, status_code=201)
def create_study(
    payload: MarketStudyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.STUDY_RUN)),
) -> MarketStudy:
    if payload.mode != "legacy":
        study = queue_opportunity_study(db, user, payload)
        background_tasks.add_task(process_queued_opportunity, study.id)
        return study
    try:
        return run_study(db, user, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{study_id}", response_model=MarketStudyOut)
def read_study(
    study_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.STUDY_READ)),
) -> MarketStudy:
    study = db.get(MarketStudy, study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Estudo não encontrado")
    return study


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
