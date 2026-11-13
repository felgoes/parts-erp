from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import FullInventory, FullOperation, FullShipment, FullShipmentItem, MarketplaceAccount

logger = logging.getLogger(__name__)


def iter_seller_inventory_links(client: MercadoLivreClient, seller_id: str):
    # The seller item scan includes paused offers so known Full stock remains visible.
    offset = 0
    while offset < 1000:
        query = urlencode({"search_type": "scan", "limit": 50, "offset": offset})
        data = client.get(f"/users/{seller_id}/items/search?{query}")
        item_ids = data.get("results", []) if isinstance(data, dict) else []
        if not item_ids:
            return
        for item_id in item_ids:
            try:
                item = client.get(f"/items/{item_id}")
            except MercadoLivreError:
                logger.info("Full item detail unavailable item_id=%s", item_id)
                continue
            if not isinstance(item, dict):
                continue
            base = {
                "item_id": str(item_id),
                "title": item.get("title"),
                "permalink": item.get("permalink"),
                "user_product_id": item.get("user_product_id"),
                "paused": item.get("status") == "paused",
            }
            inventory_id = item.get("inventory_id")
            if inventory_id:
                yield str(inventory_id), {
                    **base,
                    "variation_id": None,
                    "sku": _seller_sku(item.get("seller_custom_field"), item.get("attributes")),
                }
            for variation in item.get("variations") or []:
                inventory_id = variation.get("inventory_id")
                if inventory_id:
                    yield str(inventory_id), {
                        **base,
                        "variation_id": str(variation.get("id")) if variation.get("id") else None,
                        "sku": _seller_sku(
                            variation.get("seller_custom_field"), variation.get("attributes")
                        ),
                    }
        if len(item_ids) < 50:
            return
        offset += len(item_ids)


def _seller_sku(custom_field: Any, attributes: Any) -> str | None:
    if custom_field:
        return str(custom_field).strip() or None
    for attribute in attributes or []:
        if attribute.get("id") == "SELLER_SKU" and attribute.get("value_name"):
            return str(attribute["value_name"]).strip() or None
    return None


def inbound_reference(value: Any) -> str | None:
    if isinstance(value, dict):
        ref_type = str(value.get("type") or value.get("name") or "").lower()
        if "inbound" in ref_type:
            candidate = value.get("id") or value.get("value")
            if candidate is not None:
                return str(candidate)
        for key, child in value.items():
            if "inbound" in str(key).lower() and child is not None:
                if isinstance(child, dict):
                    candidate = child.get("id") or child.get("value")
                    if candidate is not None:
                        return str(candidate)
                else:
                    return str(child)
            nested = inbound_reference(child)
            if nested:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = inbound_reference(child)
            if nested:
                return nested
    return None


def parse_operation_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _operations_start(inventory: FullInventory) -> date:
    if inventory.operations_synced_at:
        return (inventory.operations_synced_at - timedelta(days=2)).date()
    return (datetime.now(UTC) - timedelta(days=30)).date()


def _upsert_reception_shipment(
    db: Session,
    account_id: str,
    inbound_id: str,
    inventory_id: str,
    links: list[dict[str, Any]],
) -> None:
    shipment = db.scalar(
        select(FullShipment).where(
            FullShipment.account_id == account_id, FullShipment.inbound_id == inbound_id
        )
    )
    if shipment is None:
        shipment = FullShipment(
            account_id=account_id,
            inbound_id=inbound_id,
            display_id=inbound_id,
            status="pending",
        )
        db.add(shipment)
        db.flush()
    existing = db.scalar(
        select(FullShipmentItem).where(
            FullShipmentItem.shipment_id == shipment.id,
            FullShipmentItem.inventory_id == inventory_id,
        )
    )
    if existing is not None:
        return
    candidates = links or [{}]
    unique_skus = {str(link.get("sku") or "").strip() for link in candidates if link.get("sku")}
    link = candidates[0]
    if len(unique_skus) > 1:
        link = {**link, "sku": None}
    db.add(
        FullShipmentItem(
            shipment_id=shipment.id,
            item_id=link.get("item_id"),
            variation_id=link.get("variation_id"),
            inventory_id=inventory_id,
            sku=link.get("sku"),
            product_name=link.get("title"),
            declared_quantity=None,
        )
    )


def upsert_full_operation(
    db: Session, account: MarketplaceAccount, inventory: FullInventory, payload: dict[str, Any]
) -> bool:
    operation_id = str(payload.get("id") or "")
    if not operation_id:
        return False
    refs = payload.get("external_references") or []
    inbound_id = inbound_reference(refs) or inbound_reference(payload)
    operation = db.scalar(
        select(FullOperation).where(
            FullOperation.account_id == account.id,
            FullOperation.operation_id == operation_id,
        )
    )
    if operation is None:
        operation = FullOperation(account_id=account.id, operation_id=operation_id)
        db.add(operation)
    operation.inventory_id = inventory.inventory_id
    operation.inbound_id = inbound_id
    operation.date_created = parse_operation_datetime(payload.get("date_created"))
    operation.operation_type = str(payload.get("type") or "unknown").upper()
    detail = payload.get("detail")
    operation.detail = detail if isinstance(detail, dict) else {"value": detail}
    result = payload.get("result")
    operation.result = result if isinstance(result, dict) else {"value": result}
    operation.external_references = refs
    operation.payload = payload
    operation.synced_at = datetime.now(UTC)
    if inbound_id and operation.operation_type == "INBOUND_RECEPTION":
        _upsert_reception_shipment(
            db, account.id, inbound_id, inventory.inventory_id, inventory.links or []
        )
    return True


def refresh_full_stock(client: MercadoLivreClient, inventory: FullInventory) -> None:
    stock = client.get(
        f"/inventories/{inventory.inventory_id}/stock/fulfillment?include_attributes=conditions"
    )
    if not isinstance(stock, dict) or type(stock.get("available_quantity")) is not int:
        raise ValueError("Resposta de estoque inválida")
    inventory.total = stock.get("total")
    inventory.available_quantity = stock["available_quantity"]
    inventory.not_available_quantity = stock.get("not_available_quantity")
    inventory.not_available_detail = stock.get("not_available_detail") or []
    inventory.external_references = stock.get("external_references") or []
    inventory.synced_at = datetime.now(UTC)
    inventory.sync_status = "ok"
    inventory.sync_error = None


def sync_operations_for_inventory(
    db: Session,
    client: MercadoLivreClient,
    account: MarketplaceAccount,
    inventory: FullInventory,
    date_from: date,
    date_to: date,
) -> tuple[int, bool]:
    query = urlencode(
        {
            "seller_id": account.seller_id,
            "inventory_id": inventory.inventory_id,
            "date_from": date_from.isoformat(),
            "date_to": (date_to + timedelta(days=1)).isoformat(),
            "limit": 100,
        }
    )
    path = "/stock/fulfillment/operations/search?" + query
    seen_scrolls: set[str] = set()
    operation_count = 0
    pages = 0
    while path and pages < 100:
        data = client.get(path)
        if not isinstance(data, dict):
            raise ValueError("Resposta de movimentações inválida")
        results = data.get("results") or []
        for payload in results:
            if isinstance(payload, dict) and upsert_full_operation(db, account, inventory, payload):
                operation_count += 1
        pages += 1
        scroll = (data.get("paging") or {}).get("scroll")
        if scroll and str(scroll) in seen_scrolls:
            return operation_count, False
        if not scroll:
            path = None
        else:
            seen_scrolls.add(str(scroll))
            path = "/stock/fulfillment/operations/search?" + urlencode(
                {
                    "seller_id": account.seller_id,
                    "inventory_id": inventory.inventory_id,
                    "date_from": date_from.isoformat(),
                    "date_to": (date_to + timedelta(days=1)).isoformat(),
                    "scroll": scroll,
                }
            )
    return operation_count, not path


def sync_full_account(
    account_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, int]:
    counts = {"inventories": 0, "operations": 0, "errors": 0}
    with SessionLocal() as db:
        account = db.get(MarketplaceAccount, account_id)
        if account is None or not account.active:
            return counts
        client = MercadoLivreClient(db, account)
        links_by_inventory: dict[str, list[dict[str, Any]]] = {}
        try:
            for inventory_id, link in iter_seller_inventory_links(client, account.seller_id):
                links_by_inventory.setdefault(inventory_id, [])
                if link not in links_by_inventory[inventory_id]:
                    links_by_inventory[inventory_id].append(link)
        except Exception:
            logger.exception("Full catalog synchronization failed seller_id=%s", account.seller_id)
            counts["errors"] += 1
        today = datetime.now(UTC).date()
        operation_end = min(date_to or today, today)
        for inventory_id, links in links_by_inventory.items():
            inventory = db.scalar(
                select(FullInventory).where(
                    FullInventory.account_id == account.id,
                    FullInventory.inventory_id == inventory_id,
                )
            )
            if inventory is None:
                inventory = FullInventory(account_id=account.id, inventory_id=inventory_id)
                db.add(inventory)
                db.flush()
            inventory.links = links
            try:
                refresh_full_stock(client, inventory)
                counts["inventories"] += 1
            except Exception as exc:
                inventory.sync_status = "error"
                inventory.sync_error = (
                    f"Consulta indisponível ({getattr(exc, 'status_code', None) or 'erro'})"
                )
                counts["errors"] += 1
            try:
                operation_start = date_from or _operations_start(inventory)
                if (operation_end - operation_start).days > 60:
                    raise ValueError("A janela de operações não pode superar 60 dias")
                total, complete = sync_operations_for_inventory(
                    db, client, account, inventory, operation_start, operation_end
                )
                counts["operations"] += total
                if complete:
                    inventory.operations_synced_at = datetime.now(UTC)
                    inventory.operations_coverage_start = operation_start
                    inventory.operations_coverage_end = operation_end
                    inventory.operations_sync_status = "ok"
                    inventory.operations_sync_error = None
                else:
                    inventory.operations_sync_status = "partial"
                    inventory.operations_sync_error = "Paginação incompleta"
            except Exception as exc:
                inventory.operations_sync_status = "error"
                inventory.operations_sync_error = (
                    f"Histórico indisponível ({getattr(exc, 'status_code', None) or 'erro'})"
                )
                counts["errors"] += 1
            db.commit()
    return counts
