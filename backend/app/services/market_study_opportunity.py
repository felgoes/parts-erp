from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import MarketStudy, User
from app.schemas.market_studies import MarketStudyCreate
from app.services.china_suppliers import china_supplier_provider
from app.services.company_profile import study_company_parameters
from app.services.market_opportunity_ai import explain_opportunities
from app.services.market_opportunity_candidates import (
    analyze_candidate,
    matching_products,
    scope_for,
)
from app.services.vehicle_market import vehicle_market_overview


def _company_pending(profile_missing: list[str]) -> dict[str, Any]:
    market_fields = {"margem-alvo", "comissão do canal", "percentual de devolução"}
    import_fields = {"spread cambial", "Incoterm", "modal de importação", "UF de desembaraço"}
    if market_fields & set(profile_missing):
        completion_url = "/settings/estudo"
    elif import_fields & set(profile_missing):
        completion_url = "/settings/importacao"
    elif {"regime tributário", "CNPJ"} & set(profile_missing):
        completion_url = (
            "/settings/fiscal"
            if "regime tributário" in profile_missing
            else "/settings/empresa"
        )
    else:
        completion_url = "/settings/empresa"
    return {
        "needs_company_profile": True,
        "missing_company_fields": profile_missing,
        "completion_url": completion_url,
        "message": "Complete o cadastro da empresa para calcular margem e importação.",
    }


def run_opportunity_study(
    db: Session,
    user: User,
    payload: MarketStudyCreate,
    existing: MarketStudy | None = None,
) -> MarketStudy:
    scope = scope_for(payload)
    company, missing = study_company_parameters(db)
    label = payload.study_label()
    observed_at = datetime.now(UTC)
    provider_used = None
    if missing:
        supplier_result = None
        if payload.include_suppliers_china:
            supplier = china_supplier_provider().search([])
            supplier_result = {
                "status": supplier.status,
                "source": supplier.source,
                "message": supplier.message,
                "leads": supplier.leads,
            }
        result = {
            "schema_version": "market_opportunity_result.v1",
            "observed_at": observed_at.isoformat(),
            "scope": scope,
            "company_snapshot": company,
            "company_profile_pending": _company_pending(missing),
            "executive_summary": "O estudo aguarda dados obrigatórios do cadastro da empresa.",
            "best_candidate": None,
            "candidates": [],
            "competitor_links": [],
            "supplier_research": supplier_result,
            "market_context": vehicle_market_overview(
                db,
                nationality=scope["nationality"],
                brand=scope["brand"],
            ),
            "tax_rules": {
                "status": "unavailable",
                "message": "Base fiscal por NCM não configurada; nenhuma alíquota foi presumida.",
            },
        }
    else:
        matches = matching_products(db, scope)
        candidates = []
        links: list[dict[str, Any]] = []
        provider_errors = []
        for index, (product, fitments) in enumerate(matches, start=1):
            candidate, candidate_links, external_error = analyze_candidate(
                db, product, fitments, index, company
            )
            candidates.append(candidate)
            links.extend(candidate_links)
            if external_error:
                provider_errors.append(external_error)
        candidates.sort(key=lambda row: (-row["score"], row["candidate_id"]))
        best = candidates[0] if candidates else None
        supplier_result = None
        if payload.include_suppliers_china:
            supplier_result = china_supplier_provider().search(candidates)
            supplier_result = {
                "status": supplier_result.status,
                "source": supplier_result.source,
                "message": supplier_result.message,
                "leads": supplier_result.leads,
            }
        executive = (
            "Nenhuma peça possui aplicação cadastrada para a seleção."
            if not candidates
            else (
                f"{best['part_family']} lidera a triagem, mas ainda exige cotação real "
                "e custo colocado completo."
            )
        )
        result = {
            "schema_version": "market_opportunity_result.v1",
            "observed_at": observed_at.isoformat(),
            "scope": scope,
            "company_snapshot": company,
            "company_profile_pending": None,
            "executive_summary": executive,
            "best_candidate": best,
            "candidates": candidates,
            "competitor_links": links[:30],
            "supplier_research": supplier_result,
            "market_context": vehicle_market_overview(
                db,
                nationality=scope["nationality"],
                brand=scope["brand"],
            ),
            "tax_rules": {
                "status": "unavailable",
                "message": "Base fiscal por NCM não configurada; nenhuma alíquota foi presumida.",
            },
            "partial_result": bool(provider_errors),
            "source_errors": sorted(set(provider_errors))[:3],
            "data_quality": {
                "level": "low" if provider_errors or not candidates else "medium",
                "limitations": [
                    "Emplacamentos e frota são conceitos distintos.",
                    "Anúncio publicado não é cotação firme nem fornecedor confirmado.",
                    "Sem NCM e regra fiscal, a margem permanece parcial.",
                ],
            },
        }
    if not missing and result.get("candidates"):
        result, provider_used = explain_opportunities(
            db,
            scope=scope,
            company=company,
            result=result,
            user_id=user.id,
        )
    status = (
        "pending_company_profile"
        if missing
        else "completed"
        if result.get("candidates")
        else "insufficient_data"
    )
    study = existing or MarketStudy(created_by_id=user.id)
    study.search_term = label
    study.sku = None
    study.category_id = None
    study.landed_cost = Decimal("0")
    study.target_margin_pct = Decimal(str(company.get("target_margin_pct") or "25"))
    study.marketplace_fee_pct = Decimal(str(company.get("channel_commission_pct") or "0"))
    study.shipping_cost = Decimal("0")
    study.status = status
    study.provider_used = provider_used
    study.result = result
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


def queue_opportunity_study(
    db: Session, user: User, payload: MarketStudyCreate
) -> MarketStudy:
    scope = scope_for(payload)
    study = MarketStudy(
        created_by_id=user.id,
        search_term=payload.study_label(),
        sku=None,
        category_id=None,
        landed_cost=Decimal("0"),
        target_margin_pct=Decimal("0"),
        marketplace_fee_pct=Decimal("0"),
        shipping_cost=Decimal("0"),
        status="generating",
        provider_used=None,
        result={
            "schema_version": "market_opportunity_result.v1",
            "scope": scope,
            "request_payload": payload.model_dump(mode="json"),
            "observed_at": datetime.now(UTC).isoformat(),
        },
    )
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


def process_queued_opportunity(study_id: str) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        study = db.get(MarketStudy, study_id)
        if not study or study.status != "generating":
            return
        request_payload = (study.result or {}).get("request_payload")
        user = db.get(User, study.created_by_id)
        if not request_payload or not user:
            study.status = "failed"
            study.result = {
                **(study.result or {}),
                "error": "A execução assíncrona perdeu os dados necessários.",
            }
            db.commit()
            return
        try:
            payload = MarketStudyCreate.model_validate(request_payload)
            run_opportunity_study(db, user, payload, existing=study)
        except Exception:
            db.rollback()
            failed = db.get(MarketStudy, study_id)
            if failed:
                failed.status = "failed"
                failed.result = {
                    **(failed.result or {}),
                    "error": (
                        "Não foi possível concluir o estudo. "
                        "Nenhuma nova tentativa automática foi executada."
                    ),
                }
                db.commit()
