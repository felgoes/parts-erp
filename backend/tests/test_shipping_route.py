from datetime import datetime

from app.models import MarketplaceOrder, MarketplaceOrderEvent
from app.services.shipping_route import build_shipping_route, persist_shipping_route, shipping_route_synced


def test_shipping_route_projects_only_reported_cities():
    order = MarketplaceOrder(provider="mercadolivre", shipment_id="shipment-1", payload={})
    persist_shipping_route(order, {
        "origin": {"shipping_address": {
            "city": {"name": "São Paulo"}, "state": {"id": "BR-SP"}, "street_name": "Rua privada",
        }},
        "destination": {"shipping_address": {"city": "Niterói", "state": "Rio de Janeiro"}},
    })
    # The carrier can add fields on a later sync or omit fields it returned earlier.
    persist_shipping_route(order, {"status": "shipped"})
    events = [
        MarketplaceOrderEvent(event_type="shipment_status", payload={
            "city": "Curitiba", "state": "PR", "_erp_shipment_id": "old-shipment",
        }),
        MarketplaceOrderEvent(event_type="shipment_status", payload={
            "source_date": "2026-11-08T15:00:00Z",
            "location": {"address": {"city": "Volta Redonda", "state": {"id": "BR-RJ"}, "zip_code": "00000"}},
        }, created_at=datetime(2026, 11, 8, 15)),
        MarketplaceOrderEvent(event_type="shipment_status", detail="Objeto em Niterói - RJ", payload={}),
    ]
    route = build_shipping_route(order, events)
    assert route is not None
    assert route.model_dump(mode="json") == {
        "origin": "São Paulo, SP",
        "destination": "Niterói, RJ",
        "checkpoints": [{"locality": "Volta Redonda, RJ", "recorded_at": "2026-11-08T15:00:00Z"}],
    }
    assert shipping_route_synced(order)
    order.shipment_id = "shipment-2"
    assert not shipping_route_synced(order)
    replacement = build_shipping_route(order, [])
    assert replacement is not None
    assert (replacement.origin, replacement.destination, replacement.checkpoints) == (None, None, [])


def test_status_without_location_does_not_create_checkpoint():
    order = MarketplaceOrder(provider="mercadolivre", shipment_id="shipment-1", payload={})
    event = MarketplaceOrderEvent(
        event_type="shipment_status", status="delivered", payload={"location": "Niterói, RJ"}
    )
    route = build_shipping_route(order, [event])
    assert route is not None
    assert (route.origin, route.destination, route.checkpoints) == (None, None, [])
