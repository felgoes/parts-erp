import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    InvoiceDocument,
    MarketplaceAccount,
    MarketplaceConfig,
    MarketplaceOrder,
)
from app.services.push_notifications import (
    enqueue_document_notification,
)

ORDER_RESOURCE = re.compile(r"^/orders/(?P<id>\d+)$")
PRINTABLE_LOGISTICS = {"drop_off", "xd_drop_off", "cross_docking", "self_service"}
FINISHED_FISCAL_STATUSES = {"authorized", "not_applicable"}
FINISHED_LABEL_STATUSES = {"downloaded", "completed", "not_applicable"}
TERMINAL_SHIPPING_STATUSES = {"delivered", "returned", "not_delivered", "cancelled", "canceled"}


def _resource_ids(result: dict[str, Any] | list[Any]) -> list[str]:
    if isinstance(result, dict):
        values = result.get("results") or result.get("orders") or []
        if not values and result.get("id"):
            values = [result]
    else:
        values = result
    ids: list[str] = []
    for value in values:
        raw = value.get("id") if isinstance(value, dict) else value
        if raw is not None and str(raw).strip():
            ids.append(str(raw).strip())
    return ids


def extract_invoice_order_ids(invoice: dict[str, Any]) -> set[str]:
    order_ids: set[str] = set()
    candidates = invoice.get("orders") or []
    if invoice.get("order_id"):
        candidates = [*candidates, invoice["order_id"]]
    for candidate in candidates:
        value = candidate.get("id") if isinstance(candidate, dict) else candidate
        if value:
            order_ids.add(str(value))
    for item in invoice.get("items") or []:
        if isinstance(item, dict) and item.get("external_order_id"):
            order_ids.add(str(item["external_order_id"]))
    return order_ids


def extract_sku(item: dict[str, Any]) -> str | None:
    order_item = item.get("item", {})
    if order_item.get("seller_sku"):
        return str(order_item["seller_sku"])
    if order_item.get("seller_custom_field"):
        return str(order_item["seller_custom_field"])
    for attribute in order_item.get("variation_attributes", []):
        if attribute.get("id") in {"SELLER_SKU", "SELLER_CUSTOM_FIELD"}:
            return str(attribute.get("value_name") or attribute.get("value_id") or "") or None
    return None


def is_paid(order: dict[str, Any]) -> bool:
    return order.get("status") == "paid" or any(
        payment.get("status") == "approved" for payment in order.get("payments", [])
    )


def is_cancelled(order: dict[str, Any]) -> bool:
    return str(order.get("status", "")).strip().lower() in {"cancelled", "canceled"}


def order_shipment_id(
    client: MercadoLivreClient, order_id: str, order: dict[str, Any]
) -> str | None:
    """Read shipment IDs from the current hosted Orders view, with legacy fallback."""
    try:
        result = client.get(f"/orders/{order_id}/shipments", extra_headers={"x-new-domain": "true"})
        candidates = result if isinstance(result, list) else [result]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("id"):
                return str(candidate["id"])
    except MercadoLivreError:
        # Retain compatibility while an account/app migrates to the hosted view.
        pass
    shipping = order.get("shipping") or {}
    shipment_id = shipping.get("id") if isinstance(shipping, dict) else None
    return str(shipment_id) if shipment_id else None


def _account(db: Session, seller_id: str) -> MarketplaceAccount:
    account = db.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.provider == "mercadolivre",
            MarketplaceAccount.seller_id == seller_id,
            MarketplaceAccount.active.is_(True),
        )
    )
    if not account:
        raise MercadoLivreError(f"Conta vendedora {seller_id} não conectada")
    return account


def _automation_config(db: Session) -> MarketplaceConfig | None:
    return db.scalar(select(MarketplaceConfig).limit(1))


def _parse_event_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _store_document(
    db: Session,
    invoice_id: str,
    external_id: str,
    document_type: str,
    filename: str,
    content: bytes,
) -> bool:
    existing = db.scalar(
        select(InvoiceDocument).where(
            InvoiceDocument.invoice_id == invoice_id,
            InvoiceDocument.external_id == external_id,
        )
    )
    if existing:
        return False
    base_dir = Path(get_settings().documents_dir).resolve() / invoice_id
    base_dir.mkdir(parents=True, exist_ok=True)
    path = (base_dir / filename).resolve()
    if base_dir not in path.parents:
        raise MercadoLivreError("Caminho de documento inválido")
    path.write_bytes(content)
    db.add(
        InvoiceDocument(
            invoice_id=invoice_id,
            external_id=external_id,
            document_type=document_type,
            filename=filename,
            storage_path=str(path),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    )
    db.flush()
    order = db.scalar(select(MarketplaceOrder).where(MarketplaceOrder.invoice_id == invoice_id))
    if order and document_type in {"xml", "pdf", "label_pdf"}:
        enqueue_document_notification(
            db, order, "label" if document_type == "label_pdf" else "invoice"
        )
    return True


def _fiscal_entries(result: Any) -> list[dict[str, Any]]:
    values = result if isinstance(result, list) else [result]
    return [value for value in values if isinstance(value, dict) and value.get("id")]
