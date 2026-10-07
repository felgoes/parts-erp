from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketplaceOrder, MarketplaceOrderEvent
from app.schemas.common import InvoiceOut, InvoiceTrackingEventOut, InvoiceTrackingOut


def _payload_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        timestamp = int(value)
        return datetime.fromtimestamp(timestamp, UTC) if timestamp > 0 else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return None


def tracking_last_update(order: MarketplaceOrder, events: list[MarketplaceOrderEvent]) -> tuple[datetime | None, str]:
    platform_dates: list[datetime] = []
    payload = order.payload if isinstance(order.payload, dict) else {}
    for key in ("_erp_source_updated_at", "last_updated", "update_time"):
        value = _payload_datetime(payload.get(key))
        if value:
            platform_dates.append(value)
    for event in events:
        event_payload = event.payload if isinstance(event.payload, dict) else {}
        if event_payload.get("source_date"):
            value = _payload_datetime(event_payload["source_date"])
            if value:
                platform_dates.append(value)
    if platform_dates:
        return max(platform_dates), "platform"
    fallback = order.synchronized_at or order.updated_at
    if fallback and fallback.tzinfo is None:
        fallback = fallback.replace(tzinfo=UTC)
    return fallback, "erp"


def attach_invoice_tracking(db: Session, invoices: list[InvoiceOut]) -> None:
    """Attach cached shipping state to invoice rows without making remote API calls."""
    invoice_ids = [invoice.id for invoice in invoices]
    if not invoice_ids:
        return
    orders = list(
        db.scalars(select(MarketplaceOrder).where(MarketplaceOrder.invoice_id.in_(invoice_ids)))
    )
    if not orders:
        return
    order_ids = [order.id for order in orders]
    events = list(
        db.scalars(
            select(MarketplaceOrderEvent)
            .where(
                MarketplaceOrderEvent.order_id.in_(order_ids),
                MarketplaceOrderEvent.event_type == "shipment_status",
            )
            .order_by(MarketplaceOrderEvent.created_at.asc())
        )
    )
    events_by_order: dict[str, list[InvoiceTrackingEventOut]] = {}
    raw_events_by_order: dict[str, list[MarketplaceOrderEvent]] = {}
    for event in events:
        raw_events_by_order.setdefault(event.order_id, []).append(event)
        events_by_order.setdefault(event.order_id, []).append(
            InvoiceTrackingEventOut(
                status=event.status,
                detail=event.detail,
                created_at=event.created_at,
            )
        )
    invoice_by_id = {invoice.id: invoice for invoice in invoices}
    for order in orders:
        invoice = invoice_by_id.get(order.invoice_id or "")
        if not invoice:
            continue
        order_events = raw_events_by_order.get(order.id, [])
        last_update, last_update_source = tracking_last_update(order, order_events)
        invoice.tracking = InvoiceTrackingOut(
            shipment_id=order.shipment_id,
            status=order.status,
            shipping_status=order.shipping_status,
            shipping_substatus=order.shipping_substatus,
            label_status=order.label_status,
            last_update=last_update,
            last_update_source=last_update_source,
            history=events_by_order.get(order.id, []),
        )
