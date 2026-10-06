from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketplaceOrder, MarketplaceOrderEvent
from app.schemas.common import InvoiceOut, InvoiceTrackingEventOut, InvoiceTrackingOut


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
    for event in events:
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
        invoice.tracking = InvoiceTrackingOut(
            shipment_id=order.shipment_id,
            status=order.status,
            shipping_status=order.shipping_status,
            label_status=order.label_status,
            last_update=order.synchronized_at or order.updated_at,
            history=events_by_order.get(order.id, []),
        )
