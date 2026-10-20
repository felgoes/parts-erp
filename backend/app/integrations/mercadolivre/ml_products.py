import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.ml_support import _resource_ids
from app.models import (
    MarketplaceAccount,
    Product,
    ProductMarketplaceListing,
)


def _merge_listing_images(
    product: Product,
    provider: str,
    external_item_id: str,
    pictures: list[dict],
) -> None:
    existing = list(product.images or [])
    retained = [
        row
        for row in existing
        if isinstance(row, dict)
        and not (
            row.get("source") == provider
            and row.get("external_item_id") == external_item_id
        )
    ]
    seen_urls = {str(row.get("url") or "") for row in retained}
    imported: list[dict] = []
    uploaded_at = datetime.now(UTC).isoformat()
    for picture in pictures:
        if isinstance(picture, str):
            url = picture
            width = height = 0
        elif isinstance(picture, dict):
            url = str(picture.get("secure_url") or picture.get("url") or "")
            width = int(picture.get("width") or 0)
            height = int(picture.get("height") or 0)
        else:
            continue
        if not url:
            continue
        url = url.replace("http://", "https://", 1) if url.startswith("http://") else url
        if url in seen_urls:
            continue
        seen_urls.add(url)
        imported.append(
            {
                "id": f"{provider}-{hashlib.sha256(url.encode()).hexdigest()[:20]}",
                "filename": "",
                "url": url,
                "position": len(retained) + len(imported),
                "width": width,
                "height": height,
                "uploaded_at": uploaded_at,
                "source": provider,
                "external_item_id": external_item_id,
            }
        )
    product.images = [
        {**row, "position": position}
        for position, row in enumerate([*retained, *imported])
    ]


def sync_products(db: Session, account: MarketplaceAccount) -> int:
    client = MercadoLivreClient(db, account)
    imported = 0
    offset = 0
    while True:
        result = client.get(f"/users/{account.seller_id}/items/search?offset={offset}&limit=50")
        ids = _resource_ids(result)
        if not ids:
            break
        for external_id in ids:
            detail = client.get(f"/items/{external_id}")
            if not isinstance(detail, dict):
                continue
            sku = str(
                detail.get("seller_sku")
                or detail.get("seller_custom_field")
                or next(
                    (
                        attribute.get("value_name")
                        for attribute in detail.get("attributes", [])
                        if attribute.get("id") in {"SELLER_SKU", "SELLER_CUSTOM_FIELD"}
                        and attribute.get("value_name")
                    ),
                    "",
                )
                or f"ML-{external_id}"
            )[:80]
            product = db.scalar(select(Product).where(Product.sku == sku))
            if not product and sku != f"ML-{external_id}":
                product = db.scalar(select(Product).where(Product.sku == f"ML-{external_id}"))
                if product:
                    product.sku = sku
            if not product:
                product = Product(sku=sku, name=str(detail.get("title") or sku))
                db.add(product)
                db.flush()
            product.name = str(detail.get("title") or product.name)[:200]
            product.description = detail.get("description") or product.description
            product.sale_price = Decimal(str(detail.get("price") or product.sale_price or 0))
            product.current_stock = Decimal(str(detail.get("available_quantity") or 0))
            product.active = str(detail.get("status", "active")) == "active"
            picture_payloads = [
                picture for picture in detail.get("pictures", []) if isinstance(picture, dict)
            ]
            pictures = [
                picture.get("secure_url") or picture.get("url")
                for picture in picture_payloads
                if picture.get("secure_url") or picture.get("url")
            ]
            listing = db.scalar(
                select(ProductMarketplaceListing).where(
                    ProductMarketplaceListing.provider == "mercadolivre",
                    ProductMarketplaceListing.external_item_id == external_id,
                )
            )
            if not listing:
                listing = ProductMarketplaceListing(
                    product_id=product.id,
                    provider="mercadolivre",
                    external_item_id=external_id,
                    images=pictures,
                    payload=detail,
                )
                db.add(listing)
            listing.product_id = product.id
            listing.title = str(detail.get("title") or product.name)[:200]
            listing.permalink = detail.get("permalink")
            listing.thumbnail = detail.get("thumbnail")
            listing.images = pictures
            listing.marketplace_price = Decimal(str(detail.get("price") or 0))
            listing.available_quantity = Decimal(str(detail.get("available_quantity") or 0))
            listing.sold_quantity = int(detail.get("sold_quantity") or 0)
            try:
                visits_result = MercadoLivreClient(db, account).get(
                    f"/visits/items?ids={external_id}"
                )
                if isinstance(visits_result, dict):
                    listing.visits = int(visits_result.get(external_id) or 0)
            except MercadoLivreError:
                # Métricas podem não estar habilitadas para todos os tipos de anúncio.
                pass
            listing.status = str(detail.get("status") or "unknown")
            listing.payload = detail
            listing.synchronized_at = datetime.now(UTC)
            _merge_listing_images(product, "mercadolivre", external_id, picture_payloads)
            imported += 1
        db.commit()
        offset += len(ids)
        if len(ids) < 50:
            break
    return imported


def sync_product_stock(db: Session, product: Product) -> int:
    account = db.scalar(
        select(MarketplaceAccount)
        .where(
            MarketplaceAccount.provider == "mercadolivre",
            MarketplaceAccount.active.is_(True),
        )
        .limit(1)
    )
    if not account:
        return 0
    client = MercadoLivreClient(db, account)
    updated = 0
    for listing in db.scalars(
        select(ProductMarketplaceListing).where(
            ProductMarketplaceListing.product_id == product.id,
            ProductMarketplaceListing.provider == "mercadolivre",
            ProductMarketplaceListing.external_item_id.is_not(None),
        )
    ):
        external_id = str(listing.external_item_id or "")
        if not external_id.startswith("ML") or not external_id[2:].isalnum():
            raise MercadoLivreError("Identificador do anúncio inválido; estoque não alterado")
        quantity = max(0, int(product.current_stock))
        user_product_id = (listing.payload or {}).get("user_product_id")
        result: dict | list
        if user_product_id and str(user_product_id).startswith("ML"):
            stock_data, stock_headers = client.get_with_headers(
                f"/user-products/{user_product_id}/stock"
            )
            locations = stock_data.get("locations", []) if isinstance(stock_data, dict) else []
            seller_warehouses = [
                row
                for row in locations
                if isinstance(row, dict) and row.get("type") == "seller_warehouse"
            ]
            if len(seller_warehouses) > 1:
                raise MercadoLivreError(
                    "Este User Product usa vários depósitos. Configure a distribuição do estoque "
                    "por depósito antes de sincronizar para não somar saldos incorretamente."
                )
            if len(seller_warehouses) == 1:
                location = seller_warehouses[0]
                version = stock_headers.get("x-version")
                if (
                    not version
                    or not location.get("store_id")
                    or not location.get("network_node_id")
                ):
                    raise MercadoLivreError(
                        "A API não retornou versão ou depósito válido para atualizar o estoque"
                    )
                result = client.put(
                    f"/user-products/{user_product_id}/stock/type/seller_warehouse",
                    {
                        "locations": [
                            {
                                "store_id": location["store_id"],
                                "network_node_id": location["network_node_id"],
                                "quantity": quantity,
                            }
                        ]
                    },
                    extra_headers={"x-version": version},
                )
            elif any(
                isinstance(row, dict) and row.get("type") == "meli_facility" for row in locations
            ) and not any(
                isinstance(row, dict) and row.get("type") == "selling_address" for row in locations
            ):
                raise MercadoLivreError(
                    "O estoque está em Full e é gerenciado pelo Mercado Livre; "
                    "o ERP não pode alterá-lo"
                )
            else:
                result = client.put(f"/items/{external_id}", {"available_quantity": quantity})
        else:
            result = client.put(f"/items/{external_id}", {"available_quantity": quantity})
        listing.available_quantity = product.current_stock
        listing.payload = result if isinstance(result, dict) else listing.payload
        listing.synchronized_at = datetime.now(UTC)
        updated += 1
    db.commit()
    return updated
