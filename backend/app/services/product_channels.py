from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
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
    ProductMarketplaceListing,
)
from app.schemas.common import ProductChannelDraftIn
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


def _ml_attributes(
    product: Product, draft: dict[str, Any], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    attrs: dict[str, dict[str, Any]] = {}
    for row in draft.get("attributes", []):
        if isinstance(row, dict) and row.get("id"):
            attrs[str(row["id"])] = {key: value for key, value in row.items() if value is not None}
    standard = {
        "BRAND": product.brand,
        "MODEL": product.attributes.get("model"),
        "SELLER_SKU": product.sku,
        "MPN": product.manufacturer_part_number,
        "GTIN": product.barcode,
    }
    condition_names = {
        "new": "novo",
        "used": "usado",
        "refurbished": "recondicionado",
    }
    target_condition = condition_names.get(
        draft.get("item_condition") or product.item_condition, "novo"
    )
    condition_attribute = next(
        (
            row
            for row in metadata.get("attributes", [])
            if isinstance(row, dict) and row.get("id") == "ITEM_CONDITION"
        ),
        None,
    )
    if condition_attribute:
        condition_value = next(
            (
                row
                for row in condition_attribute.get("values", [])
                if str(row.get("name", "")).casefold() == target_condition
            ),
            None,
        )
        if condition_value:
            attrs["ITEM_CONDITION"] = {
                "id": "ITEM_CONDITION",
                "value_id": condition_value.get("id"),
                "value_name": condition_value.get("name"),
            }
    for attribute_id, value in standard.items():
        if value and attribute_id not in attrs:
            attrs[attribute_id] = {"id": attribute_id, "value_name": str(value)}
    return list(attrs.values())


def _validate_ml_required(
    category_id: str,
    metadata: dict[str, Any],
    attrs: list[dict[str, Any]],
    item_condition: str,
) -> None:
    required = {
        str(row.get("id"))
        for row in metadata.get("attributes", [])
        if isinstance(row, dict)
        and (row.get("required") or (item_condition == "new" and row.get("new_required")))
    }
    sent = {str(row.get("id")) for row in attrs}
    missing = sorted(required - sent)
    if missing:
        raise ValueError(
            "Preencha os atributos obrigatórios da categoria antes de publicar: "
            + ", ".join(missing)
        )


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


def _publish_mercadolivre(
    db: Session,
    product: Product,
    listing: ProductMarketplaceListing,
    draft: dict[str, Any],
    category_id: str,
    price: Decimal,
) -> ProductMarketplaceListing:
    was_existing = bool(listing.external_item_id)
    account = _account(db, "mercadolivre")
    if not account:
        raise ValueError("Conecte o Mercado Livre em Integrações antes de publicar")
    if listing.external_item_id and listing.category_id != category_id:
        raise ValueError(
            "Não é possível trocar a categoria de um anúncio existente; crie outro anúncio"
        )
    client = MercadoLivreClient(db, account)
    metadata = channel_metadata(db, "mercadolivre", category_id=category_id)
    max_pictures = int(metadata.get("limits", {}).get("max_pictures") or 10)
    pictures = _image_bytes(product, max_pictures)
    item_condition = draft.get("item_condition") or product.item_condition
    attrs = _ml_attributes(product, draft, metadata)
    _validate_ml_required(category_id, metadata, attrs, item_condition)
    sale_terms = list(draft.get("sale_terms") or [])
    if product.warranty_days and any(
        row.get("id") == "WARRANTY_TYPE" for row in metadata.get("sale_terms", [])
    ):
        sale_terms = sale_terms or [
            {"id": "WARRANTY_TYPE", "value_name": "Garantia do vendedor"},
            {"id": "WARRANTY_TIME", "value_name": f"{product.warranty_days} dias"},
        ]
    if item_condition == "refurbished":
        warranty_terms = {row.get("id") for row in sale_terms}
        if product.warranty_days is None or product.warranty_days < 90:
            raise ValueError(
                "O Mercado Livre exige garantia mínima de 90 dias para item recondicionado"
            )
        if not {"WARRANTY_TYPE", "WARRANTY_TIME"}.issubset(warranty_terms):
            raise ValueError(
                "Informe tipo e tempo de garantia antes de publicar item recondicionado"
            )
    title = str(draft.get("title") or product.name).strip()
    if len(title) > int(metadata.get("limits", {}).get("max_title_length") or 200):
        raise ValueError("O título excede o limite de caracteres desta categoria")
    description = str(draft.get("description") or product.description or "").strip()
    uploaded = [client.upload_picture(image, filename) for filename, image in pictures]
    picture_rows = [{"id": row["id"]} for row in uploaded if row.get("id")]
    if not picture_rows:
        raise RuntimeError("O Mercado Livre não aceitou as fotos do produto")
    body: dict[str, Any] = {
        "category_id": category_id,
        "price": float(price),
        "currency_id": "BRL",
        "available_quantity": int(
            Decimal(product.current_stock).to_integral_value(rounding=ROUND_FLOOR)
        ),
        "buying_mode": "buy_it_now",
        "listing_type_id": str(draft.get("listing_type_id") or "gold_special"),
        "pictures": picture_rows,
        "attributes": attrs,
        "channels": [{"id": "marketplace"}],
    }
    if metadata.get("user_product_seller"):
        body["family_name"] = str(draft.get("family_name") or title).strip()
        if not body["family_name"]:
            raise ValueError(
                "Informe o nome genérico da família para o novo modelo do Mercado Livre"
            )
    else:
        body["title"] = title
        body["condition"] = item_condition if item_condition in {"new", "used"} else "used"
    if sale_terms:
        body["sale_terms"] = sale_terms
    if draft.get("shipping"):
        body["shipping"] = draft["shipping"]
    if any(row.get("conditional_required") for row in metadata.get("attributes", [])):
        validation_payload = {
            **body,
            "title": title,
            "condition": item_condition if item_condition in {"new", "used"} else "used",
        }
        validation_payload["description"] = {"plain_text": description} if description else {}
        validation = client.post(
            f"/categories/{category_id}/attributes/conditional", validation_payload
        )
        required_attributes = (
            validation.get("required_attributes", []) if isinstance(validation, dict) else []
        )
        submitted_ids = {str(row.get("id")) for row in attrs}
        missing_conditional = [
            str(row.get("name") or row.get("id"))
            for row in required_attributes
            if isinstance(row, dict) and str(row.get("id")) not in submitted_ids
        ]
        if missing_conditional:
            raise ValueError(
                "A categoria exige atributos adicionais para esta peça: "
                + ", ".join(missing_conditional)
            )
    if listing.external_item_id:
        is_user_product = bool(
            listing.payload.get("user_product_id")
            or "user_product_listing" in (listing.payload.get("tags") or [])
        )
        update_body = {
            key: body[key]
            for key in ("price", "available_quantity", "pictures", "attributes")
            if key in body
        }
        if is_user_product:
            if body.get("family_name"):
                update_body["family_name"] = body["family_name"]
            elif title != listing.title:
                raise ValueError(
                    "O Mercado Livre não aceita alterar title neste anúncio User Product; "
                    "configure family_name para editar o nome compartilhado."
                )
        elif body.get("title"):
            update_body["title"] = body["title"]
        else:
            update_body["title"] = title
        external = client.put(f"/items/{listing.external_item_id}", update_body)
    else:
        external = client.post("/items", body)
    if not isinstance(external, dict) or not external.get("id"):
        raise RuntimeError("O Mercado Livre não retornou o identificador do anúncio")
    listing.external_item_id = str(external["id"])
    listing.title = str(external.get("title") or title)[:200]
    listing.permalink = external.get("permalink")
    listing.thumbnail = external.get("thumbnail")
    listing.marketplace_price = Decimal(str(external.get("price") or price))
    listing.available_quantity = Decimal(str(external.get("available_quantity") or 0))
    listing.status = str(external.get("status") or "unknown")
    listing.images = [
        row.get("secure_url") or row.get("url")
        for row in external.get("pictures", [])
        if isinstance(row, dict)
    ]
    listing.category_id = category_id
    listing.payload = external
    listing.sync_status = "published"
    listing.sync_error = None
    listing.synchronized_at = datetime.now(UTC)
    if description and not was_existing:
        try:
            client.post(
                f"/items/{listing.external_item_id}/description", {"plain_text": description}
            )
        except MercadoLivreError as exc:
            listing.sync_error = f"Anúncio publicado, mas a descrição falhou: {exc}"
            listing.sync_status = "partial"
    db.commit()
    db.refresh(listing)
    return listing


def _publish_shopee(
    db: Session,
    product: Product,
    listing: ProductMarketplaceListing,
    draft: dict[str, Any],
    category_id: str,
    price: Decimal,
) -> ProductMarketplaceListing:
    account = _account(db, "shopee")
    if not account:
        raise ValueError("Conecte a Shopee em Integrações antes de publicar")
    if listing.external_item_id and listing.category_id != category_id:
        raise ValueError(
            "Não é possível trocar a categoria de um anúncio existente; crie outro anúncio"
        )
    logistics = draft.get("logistic_info") or []
    if not logistics:
        raise ValueError("Selecione ao menos uma forma de envio habilitada na Shopee")
    if not product.weight_g or not all(
        (product.package_length_cm, product.package_width_cm, product.package_height_cm)
    ):
        raise ValueError(
            "Informe o peso e as três dimensões da embalagem; não enviaremos medidas estimadas."
        )
    metadata = channel_metadata(db, "shopee", category_id=category_id)
    submitted_attributes = {
        str(row.get("id"))
        for row in draft.get("attributes", [])
        if isinstance(row, dict)
        and row.get("id")
        and (row.get("value_id") or row.get("value_name"))
    }
    missing_attributes = [
        str(row.get("name") or row.get("id"))
        for row in metadata.get("attributes", [])
        if row.get("required") and str(row.get("id")) not in submitted_attributes
    ]
    if missing_attributes:
        raise ValueError(
            "Preencha os atributos obrigatórios da Shopee: " + ", ".join(missing_attributes)
        )
    pictures = _image_bytes(product, 9)
    client = ShopeeClient.from_account(account)
    uploaded = [client.upload_product_image(image, filename) for filename, image in pictures]
    image_ids = [
        row.get("image_info", {}).get("image_id") or row.get("image_id") for row in uploaded
    ]
    image_ids = [str(image_id) for image_id in image_ids if image_id]
    if not image_ids:
        raise RuntimeError("A Shopee não retornou os identificadores das fotos")
    dimensions = {
        key: int(Decimal(str(getattr(product, field))).to_integral_value(rounding=ROUND_FLOOR))
        for key, field in (
            ("package_length", "package_length_cm"),
            ("package_width", "package_width_cm"),
            ("package_height", "package_height_cm"),
        )
    }
    body = {
        "item_name": str(draft.get("title") or product.name)[:120],
        "description": str(draft.get("description") or product.description or "")[:5000],
        "category_id": int(category_id),
        "original_price": float(price),
        "item_sku": product.sku,
        "weight": float(Decimal(str(product.weight_g)) / Decimal(1000)),
        "dimension": dimensions,
        "image": {"image_id_list": image_ids[:9]},
        "logistic_info": logistics,
        "seller_stock": [
            {"stock": int(Decimal(product.current_stock).to_integral_value(rounding=ROUND_FLOOR))}
        ],
        "attribute_list": [
            {
                "attribute_id": int(row["id"]),
                "attribute_value_list": [
                    {
                        "value_id": int(row["value_id"]) if row.get("value_id") else 0,
                        "original_value_name": str(row.get("value_name") or ""),
                    }
                ],
            }
            for row in draft.get("attributes", [])
            if row.get("id") and (row.get("value_id") or row.get("value_name"))
        ],
    }
    if product.barcode:
        body["gtin_code"] = product.barcode
    body["condition"] = "USED" if product.item_condition == "used" else "NEW"
    if listing.external_item_id:
        model_data = client.get(
            "/api/v2/product/get_model_list",
            {"item_id": int(listing.external_item_id)},
        )
        models = model_data.get("model", []) if isinstance(model_data, dict) else []
        if len(models) > 1:
            raise ValueError(
                "Este anúncio tem variações. Para evitar misturar estoque/preço entre SKUs, "
                "cadastre o vínculo de cada variação antes de sincronizar."
            )
        model_id = int(models[0].get("model_id") or 0) if models else 0
        external = client.post(
            "/api/v2/product/update_item",
            {
                "item_id": int(listing.external_item_id),
                **{
                    key: body[key]
                    for key in (
                        "item_name",
                        "description",
                        "image",
                        "logistic_info",
                        "dimension",
                        "weight",
                    )
                },
            },
        )
        client.post(
            "/api/v2/product/update_price",
            {
                "item_id": int(listing.external_item_id),
                "price_list": [{"model_id": model_id, "original_price": float(price)}],
            },
        )
        client.post(
            "/api/v2/product/update_stock",
            {
                "item_id": int(listing.external_item_id),
                "stock_list": [
                    {
                        "model_id": model_id,
                        "seller_stock": [
                            {
                                "stock": int(
                                    Decimal(product.current_stock).to_integral_value(
                                        rounding=ROUND_FLOOR
                                    )
                                )
                            }
                        ],
                    }
                ],
            },
        )
        item_id = listing.external_item_id
    else:
        external = client.post("/api/v2/product/add_item", body)
        item_id = external.get("item_id")
    if not item_id:
        raise RuntimeError("A Shopee não retornou o identificador do anúncio")
    listing.external_item_id = str(item_id)
    listing.title = body["item_name"]
    listing.marketplace_price = price
    listing.available_quantity = product.current_stock
    listing.status = str(external.get("item_status") or "NORMAL")
    listing.category_id = category_id
    listing.permalink = external.get("item_url")
    listing.images = image_ids
    listing.payload = external
    listing.sync_status = "published"
    listing.sync_error = None
    listing.synchronized_at = datetime.now(UTC)
    db.commit()
    db.refresh(listing)
    return listing
