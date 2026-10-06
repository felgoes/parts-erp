import ipaddress
import json
import statistics
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    InvoiceItem,
    InvoiceStatus,
    MarketplaceAccount,
    MarketplaceConfig,
    MarketStudy,
    MarketStudyConnectorConfig,
    Product,
    PurchaseCase,
    PurchaseEvent,
    PurchaseItem,
    SalesInvoice,
    User,
)


class ResearchProvider(Protocol):
    name: str

    def analyze(self, model: str, api_key: str, prompt: str) -> dict[str, Any]: ...


def _safe_ai_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("A IA não retornou uma análise estruturada") from None
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("A análise da IA veio em um formato inesperado")
    return parsed


class OpenAIResponsesProvider:
    name = "openai_responses"

    def analyze(self, model: str, api_key: str, prompt: str) -> dict[str, Any]:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "store": False,
                "instructions": (
                    "Você é analista de mercado de autopeças no Brasil. "
                    "Use exclusivamente os dados "
                    "fornecidos; diferencie evidência de hipótese; nunca invente giro mensal, "
                    "fornecedor ou compatibilidade. Devolva JSON com summary (string), "
                    "opportunities (array de strings), risks (array de strings), "
                    "next_steps (array de strings) e confidence (low|medium|high)."
                ),
                "input": prompt,
                "max_output_tokens": 900,
            },
            timeout=45.0,
        )
        if not response.is_success:
            raise RuntimeError(f"Provedor de IA respondeu HTTP {response.status_code}")
        body = response.json()
        text = body.get("output_text")
        if not isinstance(text, str):
            text = "\n".join(
                part.get("text", "")
                for output in body.get("output", [])
                if isinstance(output, dict)
                for part in output.get("content", [])
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        return _safe_ai_json(text)


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def analyze(self, model: str, api_key: str, prompt: str, base_url: str) -> dict[str, Any]:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Você é analista de mercado de autopeças no Brasil. "
                            "Use apenas evidências recebidas e não invente fornecedores, giro ou "
                            "compatibilidade. Responda "
                            "JSON com summary, opportunities, risks, next_steps e confidence."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=45.0,
        )
        if not response.is_success:
            raise RuntimeError(f"Provedor compatível respondeu HTTP {response.status_code}")
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return _safe_ai_json(content) if isinstance(content, str) else {}


_PROVIDERS: dict[str, Any] = {
    OpenAIResponsesProvider.name: OpenAIResponsesProvider(),
    OpenAICompatibleProvider.name: OpenAICompatibleProvider(),
}


def validate_connector_url(provider: str, value: str | None) -> str | None:
    if provider == "openai_responses":
        return "https://api.openai.com/v1"
    if not value:
        raise ValueError("Informe o endereço HTTPS do provedor compatível")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(
            "O conector personalizado precisa usar HTTPS e não aceitar credenciais na URL"
        )
    hostname = parsed.hostname.lower()
    if (
        hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith((".local", ".internal", ".localhost"))
        or all(character in "0123456789." for character in hostname)
    ):
        raise ValueError("Não é permitido apontar o conector para endereços locais ou internos")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Não é permitido apontar o conector para IP privado ou reservado")
    if parsed.query or parsed.fragment:
        raise ValueError("A URL base não deve conter parâmetros ou fragmentos")
    return value.strip().rstrip("/")


def connector_config(db: Session) -> MarketStudyConnectorConfig | None:
    return db.scalar(
        select(MarketStudyConnectorConfig).order_by(MarketStudyConnectorConfig.created_at).limit(1)
    )


def connector_output(config: MarketStudyConnectorConfig | None) -> dict[str, Any]:
    if not config:
        return {
            "provider": "openai_responses",
            "model": "gpt-6-luna",
            "base_url": None,
            "enabled": False,
            "configured": False,
            "has_api_key": False,
        }
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "enabled": config.enabled,
        "configured": bool(config.encrypted_api_key),
        "has_api_key": bool(config.encrypted_api_key),
    }


def save_connector(
    db: Session,
    *,
    provider: str,
    model: str,
    base_url: str | None,
    api_key: str | None,
    enabled: bool,
) -> MarketStudyConnectorConfig:
    from app.core.security import encrypt_secret

    normalized_url = validate_connector_url(provider, base_url)
    config = connector_config(db)
    if config is None:
        config = MarketStudyConnectorConfig()
        db.add(config)
    config.provider = provider
    config.model = model.strip()
    config.base_url = normalized_url
    config.enabled = enabled
    if api_key and api_key.strip():
        config.encrypted_api_key = encrypt_secret(api_key.strip())
    if enabled and not config.encrypted_api_key:
        raise ValueError("Informe a chave de API antes de ativar a análise com IA")
    db.flush()
    return config


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        return Decimal(str(value)) if value is not None else default
    except (InvalidOperation, ValueError):
        return default


def _similarity(query: str, title: str) -> float:
    tokens = {token.casefold() for token in query.split() if len(token) > 2}
    if not tokens:
        return 0.0
    title_tokens = {token.casefold() for token in title.split()}
    return len(tokens & title_tokens) / len(tokens)


def _mercadolivre_market_data(
    db: Session, query: str, category_id: str | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    account = db.scalar(
        select(MarketplaceAccount)
        .where(MarketplaceAccount.provider == "mercadolivre", MarketplaceAccount.active.is_(True))
        .order_by(MarketplaceAccount.created_at)
        .limit(1)
    )
    if not account:
        raise ValueError(
            "Conecte sua conta do Mercado Livre em Integrações para pesquisar o mercado"
        )
    client = MercadoLivreClient(db, account)
    config = db.scalar(select(MarketplaceConfig).limit(1))
    site_id = config.site_id if config else "MLB"
    params: dict[str, str | int] = {"q": query, "limit": 50}
    if category_id:
        params["category"] = category_id
    try:
        search = client.get(f"/sites/{site_id}/search?{urlencode(params)}")
    except (MercadoLivreError, httpx.HTTPError) as exc:
        raise RuntimeError(f"Não foi possível consultar anúncios do Mercado Livre: {exc}") from exc
    results = search.get("results", []) if isinstance(search, dict) else []
    competitors = []
    for row in results if isinstance(results, list) else []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")[:250]
        seller = row.get("seller") if isinstance(row.get("seller"), dict) else {}
        price = _decimal(row.get("price"))
        if price <= 0 or not title:
            continue
        competitors.append(
            {
                "id": str(row.get("id") or ""),
                "title": title,
                "price": str(price),
                "available_quantity_reference": row.get("available_quantity"),
                "sold_quantity_lifetime": row.get("sold_quantity"),
                "seller_id": str(seller.get("id") or "") or None,
                "permalink": str(row.get("permalink") or "") or None,
                "thumbnail": str(row.get("thumbnail") or "") or None,
                "similarity": round(_similarity(query, title), 3),
            }
        )
    competitors.sort(
        key=lambda offer: (offer["similarity"], offer["sold_quantity_lifetime"] or 0), reverse=True
    )
    competitors = competitors[:30]
    try:
        trend_path = f"/trends/{site_id}/{category_id}" if category_id else f"/trends/{site_id}"
        trends_body = client.get(trend_path)
        trend_rows = (
            trends_body
            if isinstance(trends_body, list)
            else trends_body.get("trends", [])
            if isinstance(trends_body, dict)
            else []
        )
        trend_words = [
            {"keyword": str(row.get("keyword") or "")[:120], "url": str(row.get("url") or "")[:500]}
            for row in trend_rows
            if isinstance(row, dict) and row.get("keyword")
        ]
    except (MercadoLivreError, httpx.HTTPError):
        trend_words = []
    return competitors, trend_words[:50], site_id


def _internal_sales(db: Session, sku: str | None) -> dict[str, Any]:
    if not sku:
        return {
            "units_last_90_days": 0,
            "units_per_month": 0,
            "stock_units": 0,
            "coverage_months": None,
        }
    since = datetime.now(UTC) - timedelta(days=90)
    row = db.execute(
        select(func.coalesce(func.sum(InvoiceItem.quantity), 0))
        .join(SalesInvoice, SalesInvoice.id == InvoiceItem.invoice_id)
        .where(
            func.lower(InvoiceItem.sku) == sku.lower(),
            SalesInvoice.status == InvoiceStatus.confirmed,
            func.coalesce(SalesInvoice.issued_at, SalesInvoice.created_at) >= since,
        )
    ).scalar_one()
    product = db.scalar(select(Product).where(func.lower(Product.sku) == sku.lower()))
    units = _decimal(row)
    monthly = (units / Decimal("3")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    stock = _decimal(product.current_stock) if product else Decimal("0")
    coverage = (stock / monthly).quantize(Decimal("0.1")) if monthly > 0 else None
    return {
        "units_last_90_days": str(units),
        "units_per_month": str(monthly),
        "stock_units": str(stock),
        "coverage_months": str(coverage) if coverage is not None else None,
    }


def _analysis_prompt(query: str, result: dict[str, Any]) -> str:
    evidence = {
        "search_term": query,
        "market_metrics": result.get("market_metrics"),
        "internal_sales": result.get("internal_sales"),
        "trend_matches": result.get("trend_matches"),
        "price_scenario": result.get("price_scenario"),
        "offers": [
            {
                key: offer.get(key)
                for key in ("id", "title", "price", "sold_quantity_lifetime", "similarity")
            }
            for offer in result.get("offers", [])[:15]
        ],
        "limits": [
            "Mercado Livre may expose available quantity in broad bands, "
            "not the seller's exact stock.",
            "sold_quantity_lifetime is cumulative for an ad and cannot be "
            "treated as monthly sales.",
            "An advertiser is not a verified supplier; supplier identity "
            "and terms require manual confirmation.",
            "This is market research, not a guarantee of demand, fitment, taxes or profitability.",
        ],
    }
    return json.dumps(evidence, ensure_ascii=False)


def _clean_ai_report(report: dict[str, Any]) -> dict[str, Any]:
    def strings(key: str) -> list[str]:
        values = report.get(key)
        return (
            [str(value)[:350] for value in values[:6] if isinstance(value, str)]
            if isinstance(values, list)
            else []
        )

    confidence = report.get("confidence")
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"
    return {
        "summary": str(report.get("summary") or "A IA não produziu um resumo.")[:1500],
        "opportunities": strings("opportunities"),
        "risks": strings("risks"),
        "next_steps": strings("next_steps"),
        "confidence": confidence,
    }


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
