from sqlalchemy import select

from app.db import session as session_module
from app.models import MarketplaceOrder, Product, PushNotification
from app.services import push_notifications


def test_committed_data_change_publishes_refresh(db, monkeypatch):
    published = []

    class Publisher:
        def publish(self, channel, message):
            published.append((channel, message))

    monkeypatch.setattr(session_module, "_change_publisher", lambda: Publisher())
    with session_module.SessionLocal(bind=db.get_bind()) as session:
        session.add(Product(sku="LIVE-1", name="Peça", sale_price=10, current_stock=1))
        session.commit()
        session.commit()  # A read-only commit must not trigger another refresh.

    assert published == [("parts-erp:changes", "update")]


def test_status_push_is_deduplicated_and_waits_for_a_device(db, monkeypatch):
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="123",
        seller_id="77",
        status="paid",
        shipping_status="shipped",
        shipping_substatus="out_for_delivery",
        payload={},
    )
    db.add(order)
    db.commit()
    monkeypatch.setattr(push_notifications, "_firebase_credentials", lambda: {"project_id": "qa"})

    first = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "ready_to_ship", "dropped_off"
    )
    second = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "ready_to_ship", "dropped_off"
    )

    assert first is second
    assert "Saiu para entrega" in first.body
    assert first.status == "pending"
    assert first.attempts == 0
    assert len(list(db.scalars(select(PushNotification)))) == 1
