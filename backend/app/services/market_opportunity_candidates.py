from __future__ import annotations

import statistics
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.schemas.market_studies import MarketStudyCreate
from app.services.market_research_data import _mercadolivre_market_data
from app.services.market_research_matching import _classify_offer
from app.services.vehicle_market import nationality_for_brand


def scope_for(payload: MarketStudyCreate) -> dict[str, Any]:
    brand = (payload.brand or "").strip() or None
    nationality = (payload.nationality or "").strip() or None
    if brand and not nationality:
        nationality = nationality_for_brand(brand)
    return {
        "mode": payload.mode,
        "brand": brand,
        "nationality": nationality,
        "region": payload.region or "Brasil",
        "vehicle_categories": payload.vehicle_categories or ["automovel", "comercial_leve"],
    }


def matching_products(
    db: Session, scope: dict[str, Any], limit: int = 5
) -> list[tuple[Product, list[dict[str, Any]]]]:
    products = db.scalars(select(Product).where(Product.active.is_(True)).limit(2000)).all()
    matches: list[tuple[Product, list[dict[str, Any]]]] = []
    for product in products:
        fitments = [
            fitment
            for fitment in (product.fitments or [])
            if isinstance(fitment, dict)
            and (
                not scope.get("brand")
                or str(fitment.get("make") or "").casefold() == scope["brand"].casefold()
            )
            and (
                not scope.get("nationality")
                or nationality_for_brand(str(fitment.get("make") or ""))
                == scope["nationality"]
            )
        ]
        if fitments:
            matches.append((product, fitments))
    matches.sort(key=lambda item: (item[0].name.casefold(), item[0].sku.casefold()))
    return matches[:limit]


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except ValueError:
        return None


def _money(value: Decimal | None) -> str | None:
    return (
        str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        if value is not None
        else None
    )


def analyze_candidate(
    db: Session,
    product: Product,
    fitments: list[dict[str, Any]],
    index: int,
    company: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    oem = product.manufacturer_part_number
    query = " ".join(
        value
        for value in (
            product.name,
            product.brand,
            oem,
            fitments[0].get("model") if fitments else None,
        )
        if value
    )
    external_error = None
    try:
        offers, _, _ = _mercadolivre_market_data(db, query, product.category_id)
    except (RuntimeError, ValueError) as exc:
        offers, external_error = [], str(exc)
    comparable = []
    for offer in offers:
        compatibility = _classify_offer(offer, oem, fitments)
        offer["compatibility"] = compatibility
        if compatibility in {"oem_exact", "catalog", "fitment_confirmed"}:
            comparable.append(offer)
    comparable.sort(key=lambda row: (-float(row.get("similarity") or 0), str(row["id"])))
    comparable = comparable[:30]
    prices = [_decimal(offer.get("price")) for offer in comparable]
    prices = [price for price in prices if price is not None and price > 0]
    median = Decimal(str(statistics.median(prices))).quantize(Decimal("0.01")) if prices else None
    cost = Decimal(product.cost_price) if product.cost_price and product.cost_price > 0 else None
    commission = _decimal(company.get("channel_commission_pct"))
    fixed_fee = _decimal(company.get("fixed_sale_fee"))
    returns = _decimal(company.get("expected_return_pct"))
    unknown = [
        label
        for label, value in (
            ("custo de compra", cost),
            ("frete de entrada", None),
            ("tributos de importação por NCM", None),
            ("frete de saída", None),
            ("comissão do canal", commission),
        )
        if value is None
    ]
    partial_margin = None
    if median and median > 0 and cost is not None and commission is not None:
        known_costs = cost + median * commission / 100 + (fixed_fee or Decimal("0"))
        if returns is not None:
            known_costs += median * returns / 100
        partial_margin = ((median - known_costs) / median * 100).quantize(Decimal("0.1"))
    target = _decimal(company.get("target_margin_pct"))
    comparable_count = len(comparable)
    score = min(25, max(0, int((partial_margin or Decimal("0")) * 25 / 30)))
    score += min(10, comparable_count * 2)
    score += 5 if fitments else 0
    if cost is None:
        score = min(score, 59)
    if comparable_count < 5:
        score = min(score, 54)
    if cost is None or commission is None:
        decision = "dados_insuficientes" if not comparable_count else "negociar_fornecedor"
        gate = "custo de compra ou comissão desconhecidos"
    elif comparable_count < 5:
        decision = "validar_demanda"
        gate = "amostra de concorrência abaixo de cinco ofertas"
    elif partial_margin is not None and target is not None and partial_margin < target:
        decision = "rejeitada"
        gate = "margem parcial abaixo da meta"
    else:
        decision = "negociar_fornecedor"
        gate = "cotação real, tributos e frete ainda não validados"
    candidate = {
        "candidate_id": f"cand_{index:02d}",
        "part_family": product.category or product.name,
        "product_name": product.name,
        "sku": product.sku,
        "oem": oem,
        "models": [
            {
                "brand": fitment.get("make"),
                "model": fitment.get("model"),
                "year_from": fitment.get("year_from"),
                "year_to": fitment.get("year_to"),
            }
            for fitment in fitments
        ],
        "addressable_fleet": None,
        "offers_comparable": comparable_count,
        "market_price": {
            "median": _money(median),
            "min": _money(min(prices)) if prices else None,
            "max": _money(max(prices)) if prices else None,
        },
        "unit_economics": {
            "known_cost": _money(cost),
            "partial_contribution_margin_pct": str(partial_margin)
            if partial_margin is not None
            else None,
            "target_margin_pct": company.get("target_margin_pct"),
            "components_known": [
                name
                for name, value in (
                    ("custo de compra", cost),
                    ("comissão", commission),
                    ("tarifa fixa", fixed_fee),
                    ("devoluções", returns),
                )
                if value is not None
            ],
            "components_unknown": unknown,
            "partial": True,
        },
        "facts": [
            f"{comparable_count} anúncios compatíveis observados em "
            f"{datetime.now(UTC).date().isoformat()}.",
            f"Custo médio do ERP: {_money(cost) if cost is not None else 'não informado'}.",
        ],
        "hypotheses": [
            "A presença de anúncios compatíveis pode indicar oferta ativa, não demanda garantida."
        ],
        "limitations": [
            "Compatibilidade por texto precisa de conferência na ficha técnica.",
            "Custo colocado incompleto: frete, tributos e desembaraço não foram presumidos.",
        ],
        "risks": ["Aplicação, procedência e qualidade ainda requerem conferência."],
        "score": score,
        "confidence": "medium" if comparable_count >= 5 else "low",
        "decision": decision,
        "decision_ceiling": decision,
        "blocking_gate": gate,
        "next_validation": {
            "action": "Solicitar cotação com peso, cubagem, Incoterm e prazo.",
            "success_criteria": "Margem completa igual ou superior à meta.",
            "stop_criteria": "Custo colocado acima do preço de empate.",
        },
    }
    offers_snapshot = [
        {
            "offer_id": str(offer.get("id") or ""),
            "title": offer.get("title"),
            "url": offer.get("permalink"),
            "seller_url": None,
            "observed_price": str(offer.get("price")),
            "observed_at": datetime.now(UTC).isoformat(),
            "compatibility": offer["compatibility"],
        }
        for offer in comparable[:10]
        if offer.get("permalink")
    ]
    return candidate, offers_snapshot, external_error
