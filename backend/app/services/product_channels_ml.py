from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    Product,
    ProductMarketplaceListing,
)
from app.services.product_channels_support import (
    _account,
    _image_bytes,
    channel_metadata,
)


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
