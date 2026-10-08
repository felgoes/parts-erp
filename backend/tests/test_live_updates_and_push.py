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


def test_push_batch_respects_each_category_without_losing_recipients(db, monkeypatch):
    from app.models import PushDevice, PushPreference, User

    user = User(email="push-qa@example.com", full_name="QA", password_hash="unused")
    db.add(user)
    db.flush()
    device = PushDevice(user_id=user.id, token="mock-device")
    db.add_all([
        device,
        PushPreference(user_id=user.id, category="sales", enabled=False),
    ])
    muted = PushNotification(dedupe_key="qa-muted", title="Sale", body="QA", category="sales")
    allowed = PushNotification(dedupe_key="qa-allowed", title="System", body="QA", category="system")
    db.add_all([muted, allowed])
    db.commit()
    delivered = []
    monkeypatch.setattr(push_notifications, "_firebase_credentials", lambda: {"project_id": "qa"})
    monkeypatch.setattr(
        push_notifications, "_deliver",
        lambda credentials, devices, notification, sound_by_user=None: delivered.append(
            (notification.dedupe_key, [device.id for device in devices])
        ),
    )
    assert push_notifications.deliver_pending_notifications(db) == 2
    assert delivered == [("qa-allowed", [device.id])]
    assert muted.status == "pending"
    assert muted.attempts == 0
    assert allowed.status == "sent"
    assert allowed.sent_at is not None


def test_push_delivery_preserves_legacy_channel_and_uses_per_user_sound(db, monkeypatch):
    from app.models import PushDevice, User

    user = User(email="sound-qa@example.com", full_name="Sound QA", password_hash="unused")
    legacy = PushDevice(user=user, token="legacy-device-token-1234567890")
    modern = PushDevice(user=user, token="modern-device-token-1234567890", sound_settings_version=1)
    db.add_all([user, legacy, modern])
    db.commit()
    sent = []

    class Response:
        is_success = True
        status_code = 200
        text = ""

    monkeypatch.setattr(push_notifications, "_firebase_access_token", lambda credentials: "test-token")
    monkeypatch.setattr(
        push_notifications.httpx,
        "post",
        lambda *args, **kwargs: (sent.append(kwargs["json"]) or Response()),
    )
    notification = PushNotification(
        dedupe_key="qa-sale-sound",
        category="sales",
        title="Nova venda",
        body="Pedido QA",
        data={"type": "sale"},
    )

    push_notifications._deliver({"project_id": "qa"}, [legacy, modern], notification, {user.id: "chime"})

    assert sent[0]["message"]["android"]["notification"]["channel_id"] == "sales"
    assert sent[1]["message"]["android"]["notification"]["channel_id"] == "parts_v1_sales_chime"
    assert sent[1]["message"]["notification"]["title"] == "Nova venda"
    assert sent[1]["message"]["data"]["notification_sound"] == "chime"
