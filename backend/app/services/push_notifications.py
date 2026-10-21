"""Best-effort mobile notifications for marketplace sales.

Push delivery must never make an order webhook fail. Failed deliveries remain
pending and are retried by the worker, while the unique key prevents duplicate
alerts when a marketplace retries the same webhook.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.push_transport import _firebase_credentials, deliver as _deliver
from app.models import (
    InvoiceDocument,
    MarketplaceOrder,
    PushDevice,
    PushNotification,
    PushPreference,
    SalesInvoice,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


def _sale_copy(
    order: MarketplaceOrder, invoice: SalesInvoice | None
) -> tuple[str, str, dict[str, Any]]:
    order_number = order.external_order_id
    total = (
        f"R${float(invoice.total):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if invoice
        else ""
    )
    product_lines = []
    if invoice:
        for item in invoice.items:
            product_lines.append(f"{item.description} · {item.quantity:g} un.")
    body = " · ".join(product_lines[:3])
    if total:
        body = f"{body} · " if body else ""
        body += total
    body = f"{body} · Pedido #{order_number}" if body else f"Pedido #{order_number}"
    return (
        "Venda confirmada",
        body[:500],
        {
            "type": "sale",
            "provider": order.provider,
            "order_id": order.external_order_id,
            "invoice_id": order.invoice_id or "",
            "marketplace_order_id": order.id,
            "route": "/marketplace",
            "actions": [
                {"label": "Abrir pedido", "route": "/marketplace", "query": {"order_id": order.id}}
            ],
        },
    )


def enqueue_sale_notification(db: Session, order: MarketplaceOrder) -> PushNotification | None:
    """Persists one alert per marketplace order and immediately attempts delivery."""
    if not order.invoice_id:
        return None
    dedupe_key = f"sale:{order.provider}:{order.seller_id}:{order.external_order_id}"
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    invoice = db.get(SalesInvoice, order.invoice_id)
    title, body, data = _sale_copy(order, invoice)
    notification = PushNotification(
        dedupe_key=dedupe_key, category="sales", title=title, body=body, data=data
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification


def enqueue_attention_notification(
    db: Session,
    order: MarketplaceOrder,
    kind: str,
    event_id: str,
    title: str,
    detail: str,
) -> PushNotification | None:
    """Persist one separate alert for a claim/return milestone that needs attention."""
    dedupe_key = f"marketplace-attention:{order.provider}:{order.seller_id}:{order.external_order_id}:{kind}:{event_id}"[
        :180
    ]
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    notification = PushNotification(
        dedupe_key=dedupe_key,
        category="order_status",
        title=title[:160],
        body=f"Pedido #{order.external_order_id}: {detail}"[:500],
        data={
            "type": "marketplace_attention",
            "provider": order.provider,
            "order_id": order.external_order_id,
            "marketplace_order_id": order.id,
            "route": "/marketplace",
            "actions": [
                {"label": "Abrir pedido", "route": "/marketplace", "query": {"order_id": order.id}}
            ],
        },
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification


def enqueue_after_sale_attention(
    db: Session, order: MarketplaceOrder, topic: str, event: dict[str, Any], case_id: str
) -> None:
    kind = str(event.get("kind") or "claim")
    status = str(event.get("status") or "updated")
    enqueue_attention_notification(
        db,
        order,
        kind,
        f"{event.get('id') or case_id}:{status}",
        "Reclamação atualizada" if topic == "claims" else "Devolução atualizada",
        f"{kind}: {status}" + (f" · {event['reason']}" if event.get("reason") else ""),
    )


def enqueue_document_notification(
    db: Session, order: MarketplaceOrder, kind: str
) -> PushNotification | None:
    """Compatibility wrapper: document alerts are consolidated at the ready milestone."""
    if not order.invoice_id or kind not in {"invoice", "label"}:
        return None
    return enqueue_ready_to_ship_notification(db, order)


def enqueue_ready_to_ship_notification(
    db: Session, order: MarketplaceOrder
) -> PushNotification | None:
    """Queue the single dispatch milestone only after both files are persisted."""
    if not order.invoice_id:
        return None
    documents = list(
        db.scalars(
            select(InvoiceDocument).where(
                InvoiceDocument.invoice_id == order.invoice_id,
                InvoiceDocument.document_type.in_(("xml", "pdf", "label_pdf")),
            )
        )
    )
    invoice_doc = next((doc for doc in documents if doc.document_type == "pdf"), None)
    invoice_doc = invoice_doc or next(
        (doc for doc in documents if doc.document_type == "xml"), None
    )
    label_doc = next((doc for doc in documents if doc.document_type == "label_pdf"), None)
    if invoice_doc is None or label_doc is None:
        return None

    # Keep the requested milestone order even when both documents arrive first.
    enqueue_sale_notification(db, order)
    dedupe_key = f"ready-to-ship:{order.provider}:{order.seller_id}:{order.external_order_id}"
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    notification = PushNotification(
        dedupe_key=dedupe_key,
        category="sales",
        title="Pronto para envio",
        body=f"Pedido #{order.external_order_id}: NF-e e etiqueta disponíveis.",
        data={
            "type": "ready_to_ship",
            "provider": order.provider,
            "order_id": order.external_order_id,
            "marketplace_order_id": order.id,
            "invoice_id": order.invoice_id,
            "invoice_document_id": invoice_doc.id,
            "label_document_id": label_doc.id,
            "route": "/marketplace",
            "actions": [
                {"label": "Abrir pedido", "route": "/marketplace", "query": {"order_id": order.id}},
                {
                    "label": "Etiqueta",
                    "route": f"/document-viewer/{order.invoice_id}/{label_doc.id}",
                },
                {"label": "NF-e", "route": f"/document-viewer/{order.invoice_id}/{invoice_doc.id}"},
            ],
        },
    )
    try:
        with db.begin_nested():
            db.add(notification)
            db.flush()
    except IntegrityError:
        return db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    return notification


def _audience_user_ids(db: Session, notification: PushNotification) -> set[str] | None:
    """Restringe o aviso a administrador e gerente quando a notificação pede isso."""
    data = notification.data if isinstance(notification.data, dict) else {}
    if str(data.get("audience") or "") != "managers":
        return None
    rows = db.execute(select(User.id).where(User.role.in_((UserRole.admin, UserRole.manager))))
    return {str(row[0]) for row in rows}


def enqueue_order_status_notification(
    db: Session,
    order: MarketplaceOrder,
    previous_status: str | None,
    previous_shipping_status: str | None,
    previous_shipping_substatus: str | None,
) -> PushNotification | None:
    """Compatibility entry point for marketplace shipment milestone alerts."""
    from app.services.marketplace_order_notifications import (
        enqueue_order_status_notification as enqueue,
    )

    return enqueue(
        db, order, previous_status, previous_shipping_status, previous_shipping_substatus
    )


def deliver_pending_notifications(db: Session, only_id: str | None = None) -> int:
    query = select(PushNotification).where(
        PushNotification.status == "pending", PushNotification.attempts < MAX_ATTEMPTS
    )
    if only_id:
        query = query.where(PushNotification.id == only_id)
    notifications = list(db.scalars(query.order_by(PushNotification.created_at).limit(50)))
    if not notifications:
        return 0
    credentials = _firebase_credentials()
    if credentials is None:
        return 0
    devices = list(db.scalars(select(PushDevice).where(PushDevice.active.is_(True))))
    now = datetime.now(UTC)
    for notification in notifications:
        user_ids = {device.user_id for device in devices if device.active}
        category_preferences = list(
            db.scalars(
                select(PushPreference).where(
                    PushPreference.user_id.in_(user_ids),
                    PushPreference.category == notification.category,
                )
            )
        )
        preferences_by_user = {
            preference.user_id: preference for preference in category_preferences
        }
        disabled_users = {
            user_id for user_id, preference in preferences_by_user.items() if not preference.enabled
        }
        sound_by_user = {
            user_id: preference.sound for user_id, preference in preferences_by_user.items()
        }
        audience_users = _audience_user_ids(db, notification)
        recipients = [
            device
            for device in devices
            if device.active
            and device.user_id not in disabled_users
            and (audience_users is None or device.user_id in audience_users)
        ]
        if not recipients:
            notification.error = "Nenhum celular autorizado para receber notificações"
            continue
        notification.attempts += 1
        try:
            _deliver(credentials, recipients, notification, sound_by_user)
            notification.status = "sent"
            notification.error = None
            notification.sent_at = now
        except Exception as exc:  # noqa: BLE001 - never fail the marketplace worker
            logger.exception("Could not send mobile sale notification")
            notification.error = str(exc)[:1000]
            if notification.attempts >= MAX_ATTEMPTS:
                notification.status = "failed"
    db.commit()
    return len(notifications)
