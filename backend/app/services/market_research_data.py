import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    InvoiceItem,
    InvoiceStatus,
    MarketplaceAccount,
    MarketplaceConfig,
    Product,
    SalesInvoice,
)


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
