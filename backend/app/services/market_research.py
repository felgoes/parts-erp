import statistics
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models import (
    MarketStudy,
    Product,
    PurchaseCase,
    PurchaseEvent,
    PurchaseItem,
    User,
)
from app.services import (
    market_research_data,  # noqa: F401
    market_research_providers,  # noqa: F401
)
from app.services.market_research_data import (  # noqa: F401
    _analysis_prompt,
    _clean_ai_report,
    _decimal,
    _internal_sales,
    _mercadolivre_market_data,
    _similarity,
)
from app.services.market_research_providers import (  # noqa: F401
    _PROVIDERS,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    ResearchProvider,
    _safe_ai_json,
    connector_config,
    connector_output,
    save_connector,
    validate_connector_url,
)


def run_study(db: Session, user: User, payload: Any) -> MarketStudy:
    query = payload.search_term.strip()
    offers, trends, site_id = _mercadolivre_market_data(db, query, payload.category_id)
    comparable = [offer for offer in offers if offer["similarity"] >= 0.34]
    prices = [float(offer["price"]) for offer in comparable]
    median_price = (
        Decimal(str(statistics.median(prices))).quantize(Decimal("0.01")) if prices else None
    )
    cost = Decimal(payload.landed_cost) + Decimal(payload.shipping_cost)
    fee = Decimal(payload.marketplace_fee_pct) / Decimal("100")
    margin_target = Decimal(payload.target_margin_pct) / Decimal("100")
    required_rate = Decimal("1") - fee - margin_target
    if required_rate <= 0:
        raise ValueError("Taxa do canal e margem desejada precisam somar menos de 100%")
    target_price = (cost / required_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    break_even = (
        (cost / (Decimal("1") - fee)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if fee < 1
        else None
    )
    market_margin = (
        ((median_price * (1 - fee) - cost) / median_price * 100).quantize(Decimal("0.1"))
        if median_price
        else None
    )
    trend_matches = [trend for trend in trends if _similarity(query, trend["keyword"]) >= 0.3][:10]
    internal = _internal_sales(db, payload.sku)
    result: dict[str, Any] = {
        "marketplace": "Mercado Livre",
        "site_id": site_id,
        "observed_at": datetime.now(UTC).isoformat(),
        "market_metrics": {
            "offers_found": len(offers),
            "comparable_offers": len(comparable),
            "median_price": str(median_price) if median_price is not None else None,
            "min_price": str(min(prices)) if prices else None,
            "max_price": str(max(prices)) if prices else None,
            "sold_units_lifetime_in_comparables": sum(
                int(_decimal(offer["sold_quantity_lifetime"])) for offer in comparable
            ),
            "trend_keyword_matches": len(trend_matches),
        },
        "price_scenario": {
            "landed_cost": str(cost),
            "marketplace_fee_pct": str(payload.marketplace_fee_pct),
            "target_margin_pct": str(payload.target_margin_pct),
            "break_even_price": str(break_even) if break_even is not None else None,
            "target_price": str(target_price),
            "market_margin_at_median_pct": str(market_margin)
            if market_margin is not None
            else None,
            "competitive_at_target_price": bool(
                median_price and target_price and median_price >= target_price
            ),
        },
        "internal_sales": internal,
        "trend_matches": trend_matches,
        "offers": offers,
        "possible_sources_note": (
            "Anúncios e vendedores são pistas públicas para cotação, não fornecedores verificados."
        ),
        "data_limitations": [
            "Estoque disponível no ML pode ser aproximado em faixas.",
            "Vendas do anúncio são acumuladas e não equivalem ao giro mensal.",
            "Compatibilidade automotiva e identidade de fornecedor precisam de validação humana.",
        ],
        "ai_report": None,
    }
    config = connector_config(db)
    provider_used = None
    if config and config.enabled and config.encrypted_api_key:
        provider_used = config.provider
        prompt = _analysis_prompt(query, result)
        try:
            api_key = decrypt_secret(config.encrypted_api_key)
            provider = _PROVIDERS[config.provider]
            if config.provider == "openai_compatible":
                raw_report = provider.analyze(config.model, api_key, prompt, config.base_url or "")
            else:
                raw_report = provider.analyze(config.model, api_key, prompt)
            result["ai_report"] = _clean_ai_report(raw_report)
        except (httpx.HTTPError, RuntimeError, ValueError, KeyError):
            result["ai_report"] = {
                "error": (
                    "A análise automática por IA falhou; os indicadores de mercado "
                    "continuam disponíveis."
                )
            }
    study = MarketStudy(
        created_by_id=user.id,
        search_term=query,
        sku=payload.sku,
        category_id=payload.category_id,
        landed_cost=payload.landed_cost,
        target_margin_pct=payload.target_margin_pct,
        marketplace_fee_pct=payload.marketplace_fee_pct,
        shipping_cost=payload.shipping_cost,
        status="completed" if comparable else "insufficient_data",
        provider_used=provider_used,
        result=result,
    )
    db.add(study)
    db.commit()
    db.refresh(study)
    return study


def convert_study_to_purchase(
    db: Session, study: MarketStudy, user: User, *, sku: str, quantity: Decimal
) -> PurchaseCase:
    if study.linked_purchase_id:
        purchase = db.get(PurchaseCase, study.linked_purchase_id)
        if purchase:
            return purchase
    cost = Decimal(study.landed_cost) + Decimal(study.shipping_cost)
    product = db.scalar(select(Product).where(func.lower(Product.sku) == sku.lower()))
    purchase = PurchaseCase(
        number=f"COM-{datetime.now(UTC):%Y}-{uuid4().hex[:6].upper()}",
        status="negotiating",
        notes=(
            f"Criada a partir do estudo {study.id}. Pesquise e registre cotações antes de aprovar."
        ),
    )
    purchase.items.append(
        PurchaseItem(
            product_id=product.id if product else None,
            sku=sku,
            description=study.search_term,
            quantity=quantity,
            unit_cost=cost,
        )
    )
    db.add(purchase)
    db.flush()
    study.linked_purchase_id = purchase.id
    db.add(
        PurchaseEvent(
            purchase_id=purchase.id,
            event_type="created_from_market_study",
            detail=f"Negociação aberta a partir do estudo de mercado por {user.full_name}.",
        )
    )
    db.flush()
    db.commit()
    db.refresh(purchase)
    return purchase
