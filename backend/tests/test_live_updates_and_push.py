from sqlalchemy import select

from app.db import session as session_module
from app.models import MarketplaceOrder, Product, PushNotification, SalesInvoice
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
        shipping_status="delayed",
        shipping_substatus="delayed",
        payload={},
    )
    db.add(order)
    db.commit()
    monkeypatch.setattr(push_notifications, "_firebase_credentials", lambda: {"project_id": "qa"})

    first = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "shipped", "in_hub"
    )
    second = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "shipped", "in_hub"
    )

    assert first is second
    assert "Entrega atrasada" in first.body
    assert first.status == "pending"
    assert first.attempts == 0
    assert len(list(db.scalars(select(PushNotification)))) == 1


def test_push_batch_respects_each_category_without_losing_recipients(db, monkeypatch):
    from app.models import PushDevice, PushPreference, User

    user = User(email="push-qa@example.com", full_name="QA", password_hash="unused")
    db.add(user)
    db.flush()
    device = PushDevice(user_id=user.id, token="mock-device")
    db.add_all(
        [
            device,
            PushPreference(user_id=user.id, category="sales", enabled=False),
        ]
    )
    muted = PushNotification(dedupe_key="qa-muted", title="Sale", body="QA", category="sales")
    allowed = PushNotification(
        dedupe_key="qa-allowed", title="System", body="QA", category="system"
    )
    backup = PushNotification(dedupe_key="qa-backup", title="Backup", body="QA", category="backup")
    db.add_all([muted, allowed, backup])
    db.commit()
    delivered = []
    monkeypatch.setattr(push_notifications, "_firebase_credentials", lambda: {"project_id": "qa"})
    monkeypatch.setattr(
        push_notifications,
        "_deliver",
        lambda credentials, devices, notification, sound_by_user=None: delivered.append(
            (notification.dedupe_key, [device.id for device in devices])
        ),
    )
    assert push_notifications.deliver_pending_notifications(db) == 3
    assert delivered == [("qa-allowed", [device.id]), ("qa-backup", [device.id])]
    assert muted.status == "pending"
    assert muted.attempts == 0
    assert allowed.status == "sent"
    assert allowed.sent_at is not None
    assert backup.status == "sent"


def test_normal_mercadolivre_tracking_updates_do_not_create_push(db):
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="tracking-1",
        seller_id="77",
        status="paid",
        shipping_status="in_hub",
        shipping_substatus="out_for_delivery",
        payload={},
    )
    db.add(order)
    db.commit()
    assert (
        push_notifications.enqueue_order_status_notification(
            db, order, "paid", "ready_to_ship", "ready_to_print"
        )
        is None
    )
    assert list(db.scalars(select(PushNotification))) == []


def test_mercadolivre_dispatch_handoff_and_delivery_are_the_only_tracking_milestones(db):
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="milestones-1",
        seller_id="77",
        status="paid",
        shipping_status="ready_to_ship",
        shipping_substatus="picked_up",
        payload={},
    )
    db.add(order)
    db.flush()
    started = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "ready_to_ship", "ready_to_print"
    )

    order.shipping_substatus = "in_hub"
    intermediate = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "ready_to_ship", "picked_up"
    )
    order.shipping_status = "delivered"
    order.shipping_substatus = None
    delivered = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "ready_to_ship", "in_hub"
    )
    repeated = push_notifications.enqueue_order_status_notification(
        db, order, "paid", "ready_to_ship", "in_hub"
    )

    assert started.title == "Despacho iniciado no Mercado Livre"
    assert intermediate is None
    assert delivered.title == "Pedido entregue no Mercado Livre"
    assert repeated.id == delivered.id
    assert len(list(db.scalars(select(PushNotification)))) == 2


def test_initial_mercadolivre_cancellation_creates_one_attention_alert(db):
    order = MarketplaceOrder(
        provider="mercadolivre",
        external_order_id="cancelled-1",
        seller_id="77",
        status="cancelled",
        payload={},
    )
    db.add(order)
    db.flush()
    alert = push_notifications.enqueue_order_status_notification(db, order, None, None, None)
    repeated = push_notifications.enqueue_order_status_notification(db, order, None, None, None)

    assert alert is not None
    assert alert.title == "Pedido cancelado no Mercado Livre"
    assert repeated.id == alert.id
    assert len(list(db.scalars(select(PushNotification)))) == 1


def test_sale_and_ready_alerts_are_ordered_and_deduplicated(db):
    from app.models import InvoiceDocument

    invoice = SalesInvoice(id="invoice-ready", number="VEN-READY-1", total=125)
    order = MarketplaceOrder(
        id="marketplace-ready",
        provider="mercadolivre",
        external_order_id="ready-1",
        seller_id="77",
        status="paid",
        invoice_id=invoice.id,
        payload={},
    )
    db.add_all(
        [
            invoice,
            order,
            InvoiceDocument(
                invoice_id=invoice.id,
                external_id="nf:xml",
                document_type="xml",
                filename="nf.xml",
                storage_path="/qa/nf.xml",
                sha256="a" * 64,
            ),
            InvoiceDocument(
                invoice_id=invoice.id,
                external_id="shipment:label",
                document_type="label_pdf",
                filename="label.pdf",
                storage_path="/qa/label.pdf",
                sha256="b" * 64,
            ),
        ]
    )
    db.commit()
    first = push_notifications.enqueue_ready_to_ship_notification(db, order)
    db.commit()
    second = push_notifications.enqueue_ready_to_ship_notification(db, order)
    db.commit()
    alerts = list(db.scalars(select(PushNotification).order_by(PushNotification.created_at)))
    assert first is not None and second is first
    assert [item.title for item in alerts] == ["Venda confirmada", "Pronto para envio"]
    assert [action["label"] for action in alerts[0].data["actions"]] == ["Abrir pedido"]
    assert [action["label"] for action in alerts[1].data["actions"]] == [
        "Abrir pedido",
        "Etiqueta",
        "NF-e",
    ]


def test_push_delivery_preserves_legacy_channel_and_uses_per_user_sound(db, monkeypatch):
    from app.models import PushDevice, User

    user = User(email="sound-qa@example.com", full_name="Sound QA", password_hash="unused")
    legacy = PushDevice(user=user, token="legacy-device-token-1234567890")
    modern = PushDevice(user=user, token="modern-device-token-1234567890", sound_settings_version=1)
    kaching_user = User(
        email="kaching-qa@example.com", full_name="Kaching QA", password_hash="unused"
    )
    old_kaching = PushDevice(
        user=kaching_user, token="old-kaching-device-token", sound_settings_version=1
    )
    new_kaching = PushDevice(
        user=kaching_user, token="new-kaching-device-token", sound_settings_version=2
    )
    db.add_all([user, legacy, modern, kaching_user, old_kaching, new_kaching])
    db.commit()
    sent = []

    class Response:
        is_success = True
        status_code = 200
        text = ""

    from app.services import push_transport

    monkeypatch.setattr(push_transport, "_firebase_access_token", lambda credentials: "test-token")
    monkeypatch.setattr(
        push_transport.httpx,
        "post",
        lambda *args, **kwargs: sent.append(kwargs["json"]) or Response(),
    )
    notification = PushNotification(
        dedupe_key="qa-sale-sound",
        category="sales",
        title="Nova venda",
        body="Pedido QA",
        data={"type": "sale"},
    )

    push_transport.deliver(
        {"project_id": "qa"},
        [legacy, modern, old_kaching, new_kaching],
        notification,
        {user.id: "chime", kaching_user.id: "kaching"},
    )

    assert sent[0]["message"]["android"]["notification"]["channel_id"] == "sales"
    assert sent[1]["message"]["android"]["notification"]["channel_id"] == "parts_v1_sales_chime"
    assert sent[1]["message"]["notification"]["title"] == "Nova venda"
    assert sent[1]["message"]["data"]["notification_sound"] == "chime"
    assert sent[2]["message"]["android"]["notification"]["channel_id"] == "sales"
    assert sent[3]["message"]["android"]["notification"]["channel_id"] == "parts_v1_sales_kaching"
    assert sent[3]["message"]["data"]["notification_sound"] == "kaching"
