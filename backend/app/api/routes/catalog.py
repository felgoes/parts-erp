from fastapi import APIRouter, Depends, Query
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Product
from app.schemas.common import CatalogListingOut, CatalogProductOut

router = APIRouter(prefix="/catalog", tags=["Catalogo publico"])


@router.get("/products", response_model=list[CatalogProductOut])
def catalog_products(
    search: str | None = None,
    limit: int = Query(default=48, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[CatalogProductOut]:
    query = (
        select(Product)
        .options(selectinload(Product.listings))
        .where(Product.active.is_(True))
        .order_by(Product.name)
    )
    products = list(db.scalars(query))
    tokens = _search_tokens(search)
    if tokens:
        products = [product for product in products if _matches(product, tokens)]
    products = products[:limit]
    return [
        CatalogProductOut(
            id=product.id,
            sku=product.sku,
            name=product.name,
            description=product.description,
            sale_price=product.sale_price,
            in_stock=product.current_stock > 0,
            listings=[_listing_out(listing) for listing in product.listings],
        )
        for product in products
    ]


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _search_tokens(value: str | None) -> list[str]:
    return [token for token in _normalize(value).split() if len(token) > 1]


def _matches(product: Product, tokens: list[str]) -> bool:
    parts = [product.name, product.sku, product.description]
    for listing in product.listings:
        parts.extend([listing.title, listing.external_item_id, listing.permalink])
        payload = listing.payload if isinstance(listing.payload, dict) else {}
        for attribute in payload.get("attributes", []):
            if isinstance(attribute, dict):
                parts.extend([attribute.get("id"), attribute.get("name"), attribute.get("value_name")])
    haystack = _normalize(" ".join(str(part or "") for part in parts))
    return all(token in haystack for token in tokens)


def _listing_out(listing) -> CatalogListingOut:
    payload = listing.payload if isinstance(listing.payload, dict) else {}
    attributes: list[dict[str, str]] = []
    for attribute in payload.get("attributes", []):
        if not isinstance(attribute, dict):
            continue
        name = str(attribute.get("name") or attribute.get("id") or "").strip()
        value = str(attribute.get("value_name") or attribute.get("value_id") or "").strip()
        if name and value:
            attributes.append({"name": name, "value": value})
    return CatalogListingOut(
        provider=listing.provider,
        external_item_id=listing.external_item_id,
        title=listing.title,
        permalink=listing.permalink,
        thumbnail=listing.thumbnail,
        images=[str(image) for image in (listing.images or []) if image],
        marketplace_price=listing.marketplace_price,
        available_quantity=listing.available_quantity,
        sold_quantity=listing.sold_quantity,
        visits=listing.visits,
        status=listing.status,
        attributes=attributes,
        synchronized_at=listing.synchronized_at,
    )
