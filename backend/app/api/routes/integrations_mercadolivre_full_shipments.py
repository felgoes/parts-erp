from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_permission
from app.core.permissions import Permission
from app.db.session import get_db
from app.models import FullOperation, FullShipment, FullShipmentEvent, FullShipmentItem, User
from app.api.routes.integrations_mercadolivre_full_common import (
    STAGES, EventIn, ShipmentIn, _account, _serialize_shipment, _valid_panel_url,
)

router = APIRouter()

@router.get("/shipments")
def shipments(
    q: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    distribution_center: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MARKETPLACE_READ)),
):
    account = _account(db)
    query = (
        select(FullShipment)
        .options(selectinload(FullShipment.items), selectinload(FullShipment.events))
        .where(FullShipment.account_id == account.id)
        .order_by(FullShipment.updated_at.desc())
    )
    if status:
        query = query.where(FullShipment.status == status)
    if distribution_center:
        query = query.where(
            FullShipment.distribution_center.ilike(f"%{distribution_center}%")
        )
    if date_from:
        query = query.where(
            FullShipment.updated_at >= datetime.combine(date_from, datetime.min.time(), UTC)
        )
    if date_to:
        query = query.where(
            FullShipment.updated_at
            < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), UTC)
        )
    rows = db.scalars(query).all()
    operations = db.scalars(
        select(FullOperation).where(
            FullOperation.account_id == account.id,
            FullOperation.operation_type == "INBOUND_RECEPTION",
        )
    ).all()
    result = [_serialize_shipment(shipment, operations) for shipment in rows]
    if q:
        result = [
            shipment
            for shipment in result
            if q.casefold()
            in (
                shipment["display_id"]
                + " "
                + str(shipment["items"])
                + " "
                + str(shipment["notes"] or "")
            ).casefold()
        ]
    return result


@router.post("/shipments")
def save_shipment(
    payload: ShipmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
):
    account = _account(db)
    panel_url = _valid_panel_url(payload.panel_url)
    shipment = None
    if payload.inbound_id:
        shipment = db.scalar(
            select(FullShipment).where(
                FullShipment.account_id == account.id,
                FullShipment.inbound_id == payload.inbound_id,
            )
        )
    if shipment is None:
        shipment = FullShipment(
            account_id=account.id,
            inbound_id=payload.inbound_id,
            display_id=payload.display_id.strip(),
            status="pending",
            created_by_id=user.id,
        )
        db.add(shipment)
        db.flush()
    shipment.display_id = payload.display_id.strip()
    shipment.delivery_mode = payload.delivery_mode
    shipment.distribution_center = payload.distribution_center
    shipment.scheduled_at = payload.scheduled_at
    shipment.expected_processing_at = payload.expected_processing_at
    shipment.physically_received_at = payload.physically_received_at
    shipment.panel_url = panel_url
    shipment.notes = payload.notes
    if payload.items:
        existing = {
            (item.inventory_id, item.variation_id, item.sku): item
            for item in shipment.items
        }
        for item_data in payload.items:
            key = (
                item_data.inventory_id,
                item_data.variation_id,
                item_data.sku,
            )
            item = existing.get(key)
            if item is None:
                item = FullShipmentItem(shipment_id=shipment.id)
                db.add(item)
            for field, value in item_data.model_dump().items():
                setattr(item, field, value)
    db.commit()
    shipment = db.scalar(
        select(FullShipment)
        .options(selectinload(FullShipment.items), selectinload(FullShipment.events))
        .where(FullShipment.id == shipment.id, FullShipment.account_id == account.id)
    )
    operations = db.scalars(
        select(FullOperation).where(
            FullOperation.account_id == account.id,
            FullOperation.operation_type == "INBOUND_RECEPTION",
        )
    ).all()
    return _serialize_shipment(shipment, operations)


@router.post("/shipments/{shipment_id}/events")
def add_event(
    shipment_id: str,
    payload: EventIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.MARKETPLACE_PROCESS)),
):
    if payload.stage not in STAGES:
        raise HTTPException(422, "Etapa inválida.")
    account = _account(db)
    shipment = db.scalar(
        select(FullShipment).where(
            FullShipment.id == shipment_id, FullShipment.account_id == account.id
        )
    )
    if shipment is None:
        raise HTTPException(404, "Envio não encontrado.")
    if payload.corrects_event_id:
        original = db.scalar(
            select(FullShipmentEvent).where(
                FullShipmentEvent.id == payload.corrects_event_id,
                FullShipmentEvent.shipment_id == shipment.id,
            )
        )
        if original is None:
            raise HTTPException(404, "Etapa a corrigir não encontrada neste envio.")
    event = FullShipmentEvent(
        shipment_id=shipment.id,
        stage=payload.stage,
        source="manual",
        operational_at=payload.operational_at,
        recorded_by_id=user.id,
        corrects_event_id=payload.corrects_event_id,
        note=payload.note,
    )
    db.add(event)
    shipment.status = payload.stage
    db.commit()
    db.refresh(event)
    return {
        "id": event.id,
        "stage": event.stage,
        "source": event.source,
        "operational_at": event.operational_at,
        "recorded_at": event.recorded_at,
        "recorded_by_id": event.recorded_by_id,
        "corrects_event_id": event.corrects_event_id,
        "note": event.note,
    }
