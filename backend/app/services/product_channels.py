from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.shopee.client import ShopeeClient
from app.models import (
    Product,
    ProductMarketplaceListing,
)
from app.schemas.common import ProductChannelDraftIn
from app.services import (
    product_channels_ml,  # noqa: F401
    product_channels_shopee,  # noqa: F401
    product_channels_support,  # noqa: F401
)
from app.services.product_channels_ml import (  # noqa: F401
    _ml_attributes,
    _publish_mercadolivre,
    _validate_ml_required,
)
from app.services.product_channels_shopee import (  # noqa: F401
    _publish_shopee,
)
from app.services.product_channels_support import (  # noqa: F401
    _account,
    _image_bytes,
    channel_metadata,
)


def save_channel_draft(
    db: Session, product: Product, provider: str, draft: ProductChannelDraftIn
) -> ProductMarketplaceListing:
    if provider not in {"mercadolivre", "shopee"}:
        raise ValueError("Canal não suportado")
    listing = db.scalar(
        select(ProductMarketplaceListing)
        .where(
            ProductMarketplaceListing.product_id == product.id,
            ProductMarketplaceListing.provider == provider,
        )
        .order_by(ProductMarketplaceListing.external_item_id.is_not(None).desc())
        .limit(1)
    )
    if listing is None:
        listing = ProductMarketplaceListing(
            product_id=product.id,
            provider=provider,
            external_item_id=None,
            images=[],
            payload={},
            channel_data={},
        )
        db.add(listing)
    elif (
        listing.external_item_id
        and listing.category_id
        and listing.category_id != draft.category_id
    ):
        raise ValueError(
            "A categoria de um anúncio publicado não pode ser alterada. "
            "Crie outro anúncio para usar uma categoria diferente."
        )
    listing.category_id = draft.category_id
    listing.title = draft.title or product.name
    listing.marketplace_price = draft.price or product.sale_price
    listing.status = "draft"
    listing.sync_status = "draft"
    listing.sync_error = None
    listing.channel_data = draft.model_dump(mode="json")
    db.flush()
    return listing


def publish_channel_listing(
    db: Session, product: Product, listing: ProductMarketplaceListing
) -> ProductMarketplaceListing:
    draft = dict(listing.channel_data or {})
    if not product.active:
        raise ValueError("Ative o produto no catálogo antes de publicar")
    category_id = str(draft.get("category_id") or listing.category_id or "")
    if not category_id:
        raise ValueError("Selecione a categoria da plataforma")
    price = Decimal(str(draft.get("price") or product.sale_price))
    if price <= 0:
        raise ValueError("Informe um preço de venda maior que zero")
    if listing.provider == "mercadolivre":
        return _publish_mercadolivre(db, product, listing, draft, category_id, price)
    if listing.provider == "shopee":
        if product.item_condition == "refurbished":
            raise ValueError(
                "A Shopee não tem mapeamento confirmado para produto recondicionado nesta loja."
            )
        return _publish_shopee(db, product, listing, draft, category_id, price)
    raise ValueError("Canal não suportado")


def sync_product_stock_all(db: Session, product: Product) -> dict[str, str]:
    """Propagate the local available balance only to explicitly linked live listings."""
    outcomes: dict[str, str] = {}
    listings = list(
        db.scalars(
            select(ProductMarketplaceListing).where(
                ProductMarketplaceListing.product_id == product.id,
                ProductMarketplaceListing.external_item_id.is_not(None),
            )
        )
    )
    synchronized_providers: set[str] = set()
    for listing in listings:
        provider = listing.provider
        if provider in synchronized_providers:
            continue
        synchronized_providers.add(provider)
        try:
            if provider == "mercadolivre":
                from app.integrations.mercadolivre.sync import sync_product_stock

                sync_product_stock(db, product)
                listing.sync_status = "published"
                listing.sync_error = None
                outcomes[listing.provider] = "sincronizado"
            elif provider == "shopee":
                account = _account(db, "shopee")
                if not account:
                    raise ValueError("Conta Shopee não conectada")
                client = ShopeeClient.from_account(account)
                item_id = int(listing.external_item_id)
                data = client.get("/api/v2/product/get_model_list", {"item_id": item_id})
                models = data.get("model", []) if isinstance(data, dict) else []
                if len(models) > 1:
                    raise ValueError(
                        "Anúncio com variações: vincule o SKU ao modelo correto "
                        "antes de sincronizar estoque"
                    )
                model_id = int(models[0].get("model_id") or 0) if models else 0
                stock = max(
                    0,
                    int(Decimal(product.current_stock).to_integral_value(rounding=ROUND_FLOOR)),
                )
                response = client.post(
                    "/api/v2/product/update_stock",
                    {
                        "item_id": item_id,
                        "stock_list": [{"model_id": model_id, "seller_stock": [{"stock": stock}]}],
                    },
                )
                listing.available_quantity = Decimal(stock)
                listing.payload = response if isinstance(response, dict) else listing.payload
                listing.sync_status = "published"
                listing.sync_error = None
                listing.synchronized_at = datetime.now(UTC)
                outcomes[listing.provider] = "sincronizado"
            else:
                continue
            db.commit()
        except Exception as exc:
            db.rollback()
            # Re-fetch after rollback, then persist the channel-specific error without
            # rolling back the stock movement that already committed locally.
            listing = db.get(ProductMarketplaceListing, listing.id)
            if listing:
                listing.sync_status = "error"
                listing.sync_error = str(exc)[:1000]
                db.commit()
            outcomes[provider] = "erro"
    return outcomes
