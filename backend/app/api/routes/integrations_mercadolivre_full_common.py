from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.core.queue import get_queue_pool
from app.db.session import get_db
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.models import (
    FullInventory,
    FullOperation,
    FullShipment,
    FullShipmentEvent,
    FullShipmentItem,
    MarketplaceAccount,
    Product,
    User,
)

STAGES = {"pending", "received", "processing", "completed", "cancelled"}
OFFICIAL_PANEL_HOSTS = {
    "mercadolivre.com.br",
    "www.mercadolivre.com.br",
    "mercadolivre.com",
    "www.mercadolivre.com",
}


class ShipmentItemIn(BaseModel):
    item_id: str | None = None
    variation_id: str | None = None
    inventory_id: str | None = None
    sku: str | None = None
    product_name: str | None = None
    declared_quantity: int = Field(ge=0)
    physical_count: int | None = Field(default=None, ge=0)
    discrepancy_note: str | None = None


class ShipmentIn(BaseModel):
    inbound_id: str | None = None
    display_id: str = Field(min_length=1, max_length=100)
    delivery_mode: str | None = None
    distribution_center: str | None = None
    scheduled_at: datetime | None = None
    expected_processing_at: datetime | None = None
    physically_received_at: datetime | None = None
    panel_url: HttpUrl | None = None
    notes: str | None = None
    items: list[ShipmentItemIn] = Field(default_factory=list)

    @field_validator("scheduled_at", "expected_processing_at", "physically_received_at")
    @classmethod
    def require_aware_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Informe o fuso horário da data.")
        return value.astimezone(UTC)


class EventIn(BaseModel):
    stage: str
    operational_at: datetime
    note: str | None = None
    corrects_event_id: str | None = None

    @field_validator("operational_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Informe o fuso horário da data.")
        return value.astimezone(UTC)


def _account(db: Session) -> MarketplaceAccount:
    account = db.scalar(
        select(MarketplaceAccount)
        .where(MarketplaceAccount.active.is_(True), MarketplaceAccount.provider == "mercadolivre")
        .order_by(MarketplaceAccount.created_at)
        .limit(1)
    )
    if account is None:
        raise HTTPException(409, "Conecte uma conta do Mercado Livre para consultar o Full.")
    return account


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

def _delta(detail: dict, kind: str) -> int:
    target = "notavailable" if kind == "not_available" else "available"

    def walk(value):
        total = 0
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = "".join(char for char in str(key).lower() if char.isalnum())
                if target in normalized and (
                    target == "notavailable" or "notavailable" not in normalized
                ):
                    raw = child
                    if isinstance(child, dict):
                        raw = next(
                            (child[name] for name in ("delta", "quantity", "value", "units") if name in child),
                            None,
                        )
                    try:
                        total += abs(int(raw))
                    except (TypeError, ValueError):
                        continue
                else:
                    total += walk(child)
        elif isinstance(value, list):
            for item in value:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or item.get("name") or "").lower()
                item_type = item_type.replace("_", "")
                if target in item_type and (
                    target == "notavailable" or "notavailable" not in item_type
                ):
                    raw = next(
                        (item[name] for name in ("delta", "quantity", "value", "units") if name in item),
                        None,
                    )
                    try:
                        total += abs(int(raw))
                    except (TypeError, ValueError):
                        continue
                else:
                    total += walk(item)
        return total

    return walk(detail or {})


def _serialize_inventory(row: FullInventory, db: Session) -> dict:
    local_stock = None
    skus = {str(link.get("sku") or "").strip() for link in row.links or [] if str(link.get("sku") or "").strip()}
    for link in row.links or []:
        if len(skus) != 1:
            break
        sku = str(link.get("sku") or "").strip()
        if not sku:
            continue
        product = db.scalar(select(Product).where(Product.sku == sku))
        if product:
            local_stock = {
                "sku": product.sku,
                "name": product.name,
                "quantity": float(product.current_stock),
            }
            break
    last_valid_sync = _utc(row.synced_at)
    stale = not last_valid_sync or last_valid_sync < datetime.now(UTC) - timedelta(minutes=60)
    return {
        "inventory_id": row.inventory_id,
        "total": row.total,
        "available_quantity": row.available_quantity,
        "not_available_quantity": row.not_available_quantity,
        "not_available_detail": row.not_available_detail or [],
        "external_references": row.external_references or [],
        "links": row.links or [],
        "local_stock": local_stock,
        "synced_at": _utc(row.synced_at),
        "sync_status": row.sync_status,
        "sync_error": row.sync_error,
        "stale": stale,
        "operations_synced_at": _utc(row.operations_synced_at),
        "operations_coverage_start": row.operations_coverage_start,
        "operations_coverage_end": row.operations_coverage_end,
        "operations_sync_status": row.operations_sync_status,
        "operations_sync_error": row.operations_sync_error,
    }


def _serialize_shipment(shipment: FullShipment, operations: list[FullOperation]) -> dict:
    shipment_ops = [
        operation
        for operation in operations
        if operation.inbound_id == shipment.inbound_id
        and operation.operation_type.upper() == "INBOUND_RECEPTION"
    ]
    items = []
    for item in shipment.items:
        matched = [
            operation
            for operation in shipment_ops
            if operation.inventory_id == item.inventory_id
        ]
        available = sum(_delta(operation.detail, "available") for operation in matched)
        unavailable = sum(
            _delta(operation.detail, "not_available") for operation in matched
        )
        confirmed = available + unavailable if matched else None
        completed_events = [event for event in shipment.events if event.stage == "completed"]
        discrepancy = (
            item.declared_quantity - confirmed
            if completed_events and confirmed is not None and item.declared_quantity is not None
            else None
        )
        items.append(
            {
                "id": item.id,
                "item_id": item.item_id,
                "variation_id": item.variation_id,
                "inventory_id": item.inventory_id,
                "sku": item.sku,
                "product_name": item.product_name,
                "declared_quantity": item.declared_quantity,
                "confirmed_quantity": confirmed,
                "available_received": available if matched else None,
                "unavailable_received": unavailable if matched else None,
                "physical_count": item.physical_count,
                "physical_difference": (
                    item.physical_count - item.declared_quantity
                    if item.physical_count is not None and item.declared_quantity is not None
                    else None
                ),
                "completion_difference": discrepancy,
                "discrepancy_note": item.discrepancy_note,
            }
        )
    timeline = [
        {
            "id": event.id,
            "stage": event.stage,
            "source": event.source,
            "operational_at": _utc(event.operational_at),
            "recorded_at": _utc(event.recorded_at),
            "recorded_by_id": event.recorded_by_id,
            "corrects_event_id": event.corrects_event_id,
            "note": event.note,
        }
        for event in shipment.events
    ]
    if shipment_ops:
        timeline.append(
            {
                "id": "api-reception",
                "stage": "api_reception",
                "source": "api",
                "operational_at": max(
                    (operation.date_created for operation in shipment_ops if operation.date_created),
                    default=None,
                ),
                "note": "Recepção registrada pelo Mercado Livre",
            }
        )
    for event in timeline:
        event["operational_at"] = _utc(event.get("operational_at"))
    timeline.sort(key=lambda event: event.get("operational_at") or datetime.min.replace(tzinfo=UTC))
    latest_manual = max(
        (event for event in shipment.events if event.source == "manual"),
        key=lambda event: event.operational_at,
        default=None,
    )
    manual_received_after_api = bool(
        shipment_ops
        and latest_manual
        and latest_manual.stage == "pending"
        and max((op.date_created for op in shipment_ops if op.date_created), default=None)
        and max(op.date_created for op in shipment_ops if op.date_created)
        > latest_manual.operational_at
    )
    return {
        "id": shipment.id,
        "inbound_id": shipment.inbound_id,
        "display_id": shipment.display_id,
        "status": shipment.status,
        "delivery_mode": shipment.delivery_mode,
        "distribution_center": shipment.distribution_center,
        "scheduled_at": _utc(shipment.scheduled_at),
        "expected_processing_at": _utc(shipment.expected_processing_at),
        "physically_received_at": _utc(shipment.physically_received_at),
        "panel_url": shipment.panel_url,
        "notes": shipment.notes,
        "updated_at": _utc(shipment.updated_at),
        "items": items,
        "timeline": timeline,
        "api_reception": bool(shipment_ops),
        "manual_stage_recorded": latest_manual is not None,
        "needs_review": manual_received_after_api,
        "last_api_reception_at": _utc(max(
            (op.date_created for op in shipment_ops if op.date_created), default=None
        )),
    }


def _valid_panel_url(value: HttpUrl | None) -> str | None:
    if value is None:
        return None
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_PANEL_HOSTS:
        raise HTTPException(422, "Use um link HTTPS oficial do Mercado Livre.")
    return str(value)
