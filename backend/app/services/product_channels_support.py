from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.shopee.client import ShopeeClient
from app.models import (
    MarketplaceAccount,
    MarketplaceConfig,
    Product,
)
from app.services.product_media import product_image_path


def _account(db: Session, provider: str) -> MarketplaceAccount | None:
    return db.scalar(
        select(MarketplaceAccount)
        .where(
            MarketplaceAccount.provider == provider,
            MarketplaceAccount.active.is_(True),
        )
        .order_by(MarketplaceAccount.created_at)
        .limit(1)
    )


def channel_metadata(
    db: Session, provider: str, *, query: str | None = None, category_id: str | None = None
) -> dict[str, Any]:
    if provider not in {"mercadolivre", "shopee"}:
        raise ValueError("Canal não suportado")
    account = _account(db, provider)
    result: dict[str, Any] = {
        "provider": provider,
        "connected": account is not None,
        "categories": [],
        "attributes": [],
        "sale_terms": [],
        "listing_types": [],
        "logistics": [],
        "limits": {},
    }
    if not account:
        return result
    if provider == "mercadolivre":
        config = db.scalar(select(MarketplaceConfig).limit(1))
        site_id = config.site_id if config else "MLB"
        client = MercadoLivreClient(db, account)
        seller = client.get(f"/users/{account.seller_id}")
        result["user_product_seller"] = bool(
            isinstance(seller, dict) and "user_product_seller" in (seller.get("tags") or [])
        )
        if query and not category_id:
            params = urlencode({"q": query.strip(), "limit": 10})
            path = f"/sites/{site_id}/domain_discovery/search?{params}"
            rows = client.get(path)
            result["categories"] = (
                [
                    {
                        "id": row.get("category_id"),
                        "name": row.get("category_name"),
                        "domain_id": row.get("domain_id"),
                        "path": row.get("path_from_root", []),
                    }
                    for row in rows
                    if isinstance(row, dict) and row.get("category_id")
                ]
                if isinstance(rows, list)
                else []
            )
            listing_types = client.get(f"/users/{account.seller_id}/available_listing_types")
            result["listing_types"] = listing_types if isinstance(listing_types, list) else []
        if category_id:
            if not category_id.startswith(site_id) or not category_id[len(site_id) :].isdigit():
                raise ValueError("Categoria do Mercado Livre inválida para esta região")
            category = client.get(f"/categories/{category_id}")
            if isinstance(category, dict):
                result["limits"] = {
                    "max_pictures": category.get("settings", {}).get("max_pictures_per_item"),
                    "max_title_length": category.get("settings", {}).get("max_title_length"),
                    "category_name": category.get("name"),
                }
            attrs = client.get(f"/categories/{category_id}/attributes")
            result["attributes"] = (
                [
                    {
                        "id": row.get("id"),
                        "name": row.get("name"),
                        "required": bool((row.get("tags") or {}).get("required")),
                        "new_required": bool((row.get("tags") or {}).get("new_required")),
                        "conditional_required": bool(
                            (row.get("tags") or {}).get("conditional_required")
                        ),
                        "value_type": row.get("value_type"),
                        "values": row.get("values", []),
                        "max_length": row.get("value_max_length"),
                    }
                    for row in attrs
                    if isinstance(row, dict) and row.get("id")
                ]
                if isinstance(attrs, list)
                else []
            )
            terms = client.get(f"/categories/{category_id}/sale_terms")
            result["sale_terms"] = terms if isinstance(terms, list) else []
            try:
                specs = client.get(f"/categories/{category_id}/technical_specs/input")
                result["technical_specs"] = specs
            except MercadoLivreError:
                result["technical_specs"] = None
        return result

    client = ShopeeClient.from_account(account)
    if not category_id:
        data = client.get("/api/v2/product/get_category", {"language": "pt-br"})
        categories = data.get("category_list", []) if isinstance(data, dict) else []
        if query:
            needle = query.casefold()
            categories = [
                row for row in categories if needle in str(row.get("category_name", "")).casefold()
            ]
        result["categories"] = [
            {
                "id": row.get("category_id"),
                "name": row.get("category_name"),
                "has_children": row.get("has_children"),
            }
            for row in categories[:50]
            if isinstance(row, dict) and row.get("category_id")
        ]
    else:
        if not category_id.isdigit():
            raise ValueError("Categoria da Shopee precisa ser numérica")
        attrs = client.get(
            "/api/v2/product/get_attributes",
            {"category_id": int(category_id), "language": "pt-br"},
        ).get("attribute_list", [])
        result["attributes"] = [
            {
                "id": row.get("attribute_id"),
                "name": row.get("attribute_name"),
                "required": bool(row.get("is_mandatory")),
                "value_type": row.get("attribute_type"),
                "values": row.get("attribute_value_list", []),
            }
            for row in attrs
            if isinstance(row, dict) and row.get("attribute_id")
        ]
        logistics = client.get("/api/v2/logistics/get_channel_list", {}).get(
            "logistics_channel_list", []
        )
        result["logistics"] = [
            {"id": row.get("logistics_channel_id"), "name": row.get("logistics_channel_name")}
            for row in logistics
            if isinstance(row, dict) and row.get("logistics_channel_id")
        ]
        result["limits"] = {"max_pictures": 9}
    return result


def _image_bytes(product: Product, max_count: int) -> list[tuple[str, bytes]]:
    images = list(product.images or [])
    if not images:
        raise ValueError("Adicione pelo menos uma foto válida antes de publicar")
    if len(images) > max_count:
        raise ValueError(f"A categoria aceita no máximo {max_count} foto(s)")
    result = []
    for row in sorted(images, key=lambda image: image.get("position", 0)):
        filename = str(row.get("filename") or "")
        path = product_image_path(filename)
        result.append((filename, path.read_bytes()))
    return result
