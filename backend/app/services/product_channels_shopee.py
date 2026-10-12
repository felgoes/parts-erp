from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.shopee.client import ShopeeClient
from app.models import (
    Product,
    ProductMarketplaceListing,
)
from app.services.product_channels_support import (
    _account,
    _image_bytes,
    channel_metadata,
)


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
