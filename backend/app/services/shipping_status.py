"""Shared Mercado Envios progress states for operational action queues."""

from sqlalchemy import func, or_, select

from app.models import MarketplaceOrderEvent

DISPATCHED_SHIPPING_SUBSTATUSES = (
    "authorized_by_carrier",
    "picked_up",
    "shipped_to_carrier",
    "dropped_off",
    "in_transit",
    "in_hub",
    "on_route",
    "out_for_delivery",
    "at_the_branch",
    "delivered",
    "returned",
    "not_delivered",
)


def shipping_progress_history_exists(order_id: object):
    """SQL EXISTS expression for a shipment that advanced past preparation once."""
    return (
        select(MarketplaceOrderEvent.id)
        .where(
            MarketplaceOrderEvent.order_id == order_id,
            MarketplaceOrderEvent.event_type == "shipment_status",
            or_(
                func.lower(MarketplaceOrderEvent.status).in_(
                    ("shipped", "delivered", "not_delivered")
                ),
                func.lower(func.coalesce(MarketplaceOrderEvent.detail, "")).in_(
                    DISPATCHED_SHIPPING_SUBSTATUSES
                ),
            ),
        )
        .exists()
    )
