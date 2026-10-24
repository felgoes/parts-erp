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
    MarketplaceConfig,
    MarketStudy,
    Product,
    ProductMarketplaceListing,
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
from app.services.market_research_matching import _classify_offer, _normalized_code
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

MIN_COMPARABLE_SAMPLE_SIZE = 5


def run_study(db: Session, user: User, payload: Any) -> MarketStudy:
    query = payload.search_term.strip()
    product = (
        db.scalar(select(Product).where(func.lower(Product.sku) == (payload.sku or "").lower()))
        if payload.sku
        else None
    )
    cost_input = payload.landed_cost
    if cost_input is None and product and product.cost_price and Decimal(product.cost_price) > 0:
        cost_input = Decimal(product.cost_price)
    cost_known = cost_input is not None and Decimal(cost_input) > 0
    fitment_terms = " ".join(
        str(value)
        for fitment in payload.fitments
        for value in (
            fitment.get("make"),
            fitment.get("model"),
            fitment.get("year_from"),
            fitment.get("year_to"),
            fitment.get("engine"),
            fitment.get("version"),
        )
        if value
    )
    category_or_term = (payload.category_id or "").strip()
    category_id = category_or_term if category_or_term.upper().startswith("MLB") else None
    search_query = " ".join(
        value
        for value in (
            query,
            payload.oem,
            payload.application,
            fitment_terms,
            category_or_term if category_or_term and not category_id else None,
        )
        if value
    )
    offers, trends, site_id = _mercadolivre_market_data(db, search_query, category_id)
    catalog_listing_ids = (
        set(
            db.scalars(
                select(ProductMarketplaceListing.external_item_id).where(
                    ProductMarketplaceListing.product_id == product.id,
                    ProductMarketplaceListing.provider == "mercadolivre",
                    ProductMarketplaceListing.external_item_id.is_not(None),
                )
            ).all()
        )
        if product
        else set()
    )
    seen: set[str] = set()
    deduplicated = []
    for offer in offers:
        identifier = (
            str(offer.get("id") or "")
            or f"{_normalized_code(str(offer.get('title') or ''))}:{offer.get('price')}"
        )
        if identifier not in seen:
            seen.add(identifier)
            offer["compatibility"] = _classify_offer(
                offer, payload.oem, payload.fitments, catalog_listing_ids
            )
            offer["compatibility_label"] = {
                "oem_exact": "OEM correspondente",
                "catalog": "Produto de catálogo",
                "fitment_confirmed": "Aplicação compatível",
                "unconfirmed": "Compatibilidade não confirmada",
            }[offer["compatibility"]]
            deduplicated.append(offer)
    priority = {"oem_exact": 0, "catalog": 1, "fitment_confirmed": 2, "unconfirmed": 3}
    deduplicated.sort(
        key=lambda offer: (priority[offer["compatibility"]], -float(offer.get("similarity") or 0))
    )
    offers = deduplicated[:50]
    comparable = [
        offer
        for offer in offers
        if offer["compatibility"] in {"oem_exact", "catalog", "fitment_confirmed"}
    ]
    prices = [
        Decimal(str(offer["price"])) for offer in comparable if _decimal(offer.get("price")) > 0
    ]
    median_price = (
        Decimal(str(statistics.median(prices))).quantize(Decimal("0.01")) if prices else None
    )
    landed = Decimal(cost_input or 0)
    inbound_known = payload.shipping_cost is not None
    inbound = Decimal(payload.shipping_cost) if inbound_known else Decimal("0")
    cost_post = landed + inbound
    marketplace_config = db.scalar(select(MarketplaceConfig).limit(1))
    fee_pct = Decimal(
        payload.marketplace_fee_pct
        if payload.marketplace_fee_pct is not None
        else marketplace_config.study_default_commission_pct
        if marketplace_config
        else "16"
    )
    fee = fee_pct / Decimal("100")
    margin_target_pct = Decimal(payload.target_margin_pct)
    margin_target = margin_target_pct / Decimal("100")
    fixed_fee_known = payload.fixed_fee is not None
    outbound_known = payload.outbound_shipping is not None
    fixed_fee = Decimal(payload.fixed_fee) if fixed_fee_known else Decimal("0")
    outbound = Decimal(payload.outbound_shipping) if outbound_known else Decimal("0")
    required_rate = Decimal("1") - fee - margin_target
    target_price = (
        ((cost_post + fixed_fee + outbound) / required_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if cost_known and inbound_known and fixed_fee_known and outbound_known and required_rate > 0
        else None
    )
    break_even_rate = Decimal("1") - fee
    break_even = (
        ((cost_post + fixed_fee + outbound) / break_even_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if cost_known
        and inbound_known
        and fixed_fee_known
        and outbound_known
        and break_even_rate > 0
        else None
    )
    market_margin = (
        (
            (
                median_price
                - landed
                - (inbound if inbound_known else Decimal("0"))
                - (median_price * fee)
                - fixed_fee
                - outbound
            )
            / median_price
            * 100
        ).quantize(Decimal("0.1"))
        if median_price and cost_known
        else None
    )
    trend_matches = [trend for trend in trends if _similarity(query, trend["keyword"]) >= 0.3][:10]
    internal = _internal_sales(db, payload.sku)
    confidence = (
        "high"
        if comparable and all(o["compatibility"] == "oem_exact" for o in comparable)
        else "medium"
        if comparable
        else "low"
    )
    small_sample = len(comparable) < MIN_COMPARABLE_SAMPLE_SIZE
    if not offers:
        conclusion = "Nenhum anúncio encontrado"
        conclusion_reason = (
            "A consulta não retornou anúncios ativos. Tente outro termo ou código OEM."
        )
    elif small_sample:
        conclusion = "Poucos anúncios comparáveis"
        conclusion_reason = (
            f"Somente {len(comparable)} anúncios têm correspondência identificável; "
            "não há base suficiente para uma recomendação conclusiva."
        )
    elif not cost_known:
        conclusion = "Dados insuficientes para estimar margem"
        conclusion_reason = (
            "A pesquisa de preços foi concluída, mas falta custo de compra para estimar a margem."
        )
    elif market_margin is not None and market_margin < 0:
        conclusion = "Preço de mercado abaixo do custo"
        conclusion_reason = "A mediana observada não cobre os custos e a comissão informados."
    elif market_margin is not None and market_margin < margin_target_pct:
        conclusion = "Margem apertada ao preço de mercado"
        conclusion_reason = (
            "A margem calculada na mediana fica abaixo da margem desejada informada."
        )
    else:
        conclusion = "Oportunidade para investigar"
        conclusion_reason = (
            "Os indicadores justificam conferir aplicação, condições dos anúncios "
            "e cotações antes de decidir."
        )
    result: dict[str, Any] = {
        "marketplace": "Mercado Livre",
        "site_id": site_id,
        "observed_at": datetime.now(UTC).isoformat(),
        "product_context": {
            "oem": payload.oem,
            "application": payload.application,
            "fitments": payload.fitments,
        },
        "market_metrics": {
            "offers_found": len(offers),
            "consulted_limit": 50,
            "comparable_offers": len(comparable),
            "median_price": str(median_price) if median_price is not None else None,
            "min_price": str(min(prices)) if prices else None,
            "max_price": str(max(prices)) if prices else None,
            "sample_confidence": confidence,
            "small_sample": small_sample,
            "conclusion": conclusion,
            "conclusion_reason": conclusion_reason,
            "sold_units_lifetime_in_comparables": sum(
                int(_decimal(o.get("sold_quantity_lifetime"))) for o in comparable
            ),
            "trend_keyword_matches": len(trend_matches),
        },
        "price_scenario": {
            "landed_cost": str(landed) if cost_known else None,
            "inbound_shipping": str(inbound) if inbound_known else None,
            "cost_post": str(cost_post) if cost_known and inbound_known else None,
            "cost_known": cost_known,
            "inbound_shipping_known": inbound_known,
            "marketplace_fee_pct": str(fee_pct),
            "commission_pct": str(fee_pct),
            "fixed_fee": str(fixed_fee) if fixed_fee_known else None,
            "outbound_shipping": str(outbound) if outbound_known else None,
            "fixed_fee_known": fixed_fee_known,
            "outbound_shipping_known": outbound_known,
            "unknown_components": [
                name
                for name, known in (
                    ("custo de compra", cost_known),
                    ("frete de entrada rateado", inbound_known),
                    ("tarifa fixa", fixed_fee_known),
                    ("frete de saída", outbound_known),
                )
                if not known
            ],
            "target_margin_pct": str(margin_target_pct),
            "break_even_price": str(break_even) if break_even is not None else None,
            "target_price": str(target_price) if target_price is not None else None,
            "market_margin_at_median_pct": str(market_margin)
            if market_margin is not None
            else None,
            "competitive_at_target_price": bool(
                median_price and target_price and median_price >= target_price
            ),
            "calculation_components": (["custo de compra"] if cost_known else [])
            + (["frete de entrada rateado"] if inbound_known else [])
            + ["comissão percentual"]
            + (["tarifa fixa"] if fixed_fee_known else [])
            + (["frete de saída"] if outbound_known else []),
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
            "Compatibilidade baseada em texto precisa ser validada na ficha técnica e no catálogo.",
        ],
        "ai_report": None,
    }
    config = connector_config(db)
    provider_used = None
    if config and config.enabled and config.encrypted_api_key:
        provider_used = config.provider
        try:
            api_key = decrypt_secret(config.encrypted_api_key)
            provider = _PROVIDERS[config.provider]
            prompt = _analysis_prompt(query, result)
            raw_report = (
                provider.analyze(config.model, api_key, prompt, config.base_url or "")
                if config.provider == "openai_compatible"
                else provider.analyze(config.model, api_key, prompt)
            )
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
        landed_cost=landed if cost_known else Decimal("0"),
        target_margin_pct=margin_target_pct,
        marketplace_fee_pct=fee_pct,
        shipping_cost=inbound if inbound_known else Decimal("0"),
        status="completed" if not small_sample and comparable else "insufficient_data",
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
            + (
                " Custo de referência não informado; defina-o ao cotar."
                if not study.result.get("price_scenario", {}).get("cost_known")
                else ""
            )
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
