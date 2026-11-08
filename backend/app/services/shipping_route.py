from collections.abc import Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketplaceOrder, MarketplaceOrderEvent
from app.schemas.shipping_route import ShippingCheckpointOut, ShippingRouteOut
from app.services.tracking_destination import (
    shipping_address_locality,
    shipping_destination_locality,
    tracking_destination_locality,
)

ROUTE_KEY = "_erp_shipping_route"


def _locality(place: object) -> str | None:
    if not isinstance(place, Mapping):
        return None
    return (
        shipping_address_locality(place.get("shipping_address"))
        or shipping_address_locality(place.get("address"))
        or shipping_address_locality(place)
    )


def _metadata(order: MarketplaceOrder) -> dict | None:
    payload = order.payload if isinstance(order.payload, dict) else {}
    meta = payload.get(ROUTE_KEY)
    if isinstance(meta, dict) and meta.get("shipment_id") == order.shipment_id:
        return meta
    return None


def shipping_route_synced(order: MarketplaceOrder) -> bool:
    return _metadata(order) is not None


def persist_shipping_route(order: MarketplaceOrder, shipment: Mapping) -> None:
    previous = _metadata(order) or {}
    metadata = {
        "shipment_id": order.shipment_id,
        "origin": (
            _locality(shipment.get("origin"))
            or _locality(shipment.get("sender_address"))
            or previous.get("origin")
        ),
        "destination": shipping_destination_locality(shipment) or previous.get("destination"),
    }
    if metadata != previous:
        order.payload = {**(order.payload or {}), ROUTE_KEY: metadata}


def build_shipping_route(
    order: MarketplaceOrder, events: Iterable[MarketplaceOrderEvent]
) -> ShippingRouteOut | None:
    if order.provider != "mercadolivre" or not order.shipment_id:
        return None
    metadata = _metadata(order)
    checkpoints = []
    for event in events:
        payload = event.payload or {}
        if event.event_type != "shipment_status":
            continue
        shipment_id = payload.get("_erp_shipment_id") or payload.get("shipment_id")
        if shipment_id is not None and str(shipment_id) != order.shipment_id:
            continue
        locality = (
            _locality(payload.get("location"))
            or _locality(payload.get("facility"))
            or shipping_address_locality(payload)
        )
        if locality:
            checkpoints.append(
                ShippingCheckpointOut(
                    locality=locality,
                    recorded_at=event.created_at if payload.get("source_date") else None,
                )
            )
    legacy_destination = (
        tracking_destination_locality(order) if ROUTE_KEY not in (order.payload or {}) else None
    )
    return ShippingRouteOut(
        origin=metadata.get("origin") if metadata else None,
        destination=metadata.get("destination") if metadata is not None else legacy_destination,
        checkpoints=checkpoints[-40:],
    )


def load_shipping_route(db: Session, order: MarketplaceOrder) -> ShippingRouteOut | None:
    if order.provider != "mercadolivre" or not order.shipment_id:
        return None
    events = db.scalars(
        select(MarketplaceOrderEvent)
        .where(
            MarketplaceOrderEvent.order_id == order.id,
            MarketplaceOrderEvent.event_type == "shipment_status",
        )
        .order_by(MarketplaceOrderEvent.created_at, MarketplaceOrderEvent.id)
    )
    return build_shipping_route(order, events)
