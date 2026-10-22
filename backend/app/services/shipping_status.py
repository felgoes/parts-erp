"""Shared Mercado Envios states used for operational action queues."""

DISPATCHED_SHIPPING_SUBSTATUSES = (
    "in_pickup_list",
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
