"""Best-effort mobile notifications for marketplace sales.

Push delivery must never make an order webhook fail. Failed deliveries remain
pending and are retried by the worker, while the unique key prevents duplicate
alerts when a marketplace retries the same webhook.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import MarketplaceOrder, PushDevice, PushNotification, SalesInvoice

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


_access_token = ""
_access_token_expires_at = 0.0


def _firebase_credentials() -> dict[str, Any] | None:
    """Loads the credential locally without ever exposing its contents."""
    credential_file = get_settings().firebase_service_account_file.strip()
    if not credential_file:
        return None
    path = Path(credential_file).expanduser()
    if not path.is_file():
        logger.warning("Firebase credential file is unavailable")
        return None
    try:
        credentials = json.loads(path.read_text(encoding="utf-8"))
        if not all(
            credentials.get(field) for field in ("client_email", "private_key", "project_id")
        ):
            raise ValueError("service account incompleta")
        return credentials
    except Exception:  # noqa: BLE001 - notification transport must not halt sales sync
        logger.exception("Could not load Firebase push credential")
        return None


def _firebase_access_token(credentials: dict[str, Any]) -> str:
    global _access_token, _access_token_expires_at
    if _access_token and _access_token_expires_at > time.time() + 60:
        return _access_token
    issued_at = int(time.time())
    assertion = jwt.encode(
        {
            "iss": credentials["client_email"],
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": issued_at,
            "exp": issued_at + 3600,
        },
        credentials["private_key"],
        algorithm="RS256",
    )
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    _access_token = str(payload["access_token"])
    _access_token_expires_at = time.time() + int(payload.get("expires_in", 3600))
    return _access_token


def _sale_copy(
    order: MarketplaceOrder, invoice: SalesInvoice | None
) -> tuple[str, str, dict[str, str]]:
    provider = "Mercado Livre" if order.provider == "mercadolivre" else "Shopee"
    order_number = order.external_order_id
    customer_name = invoice.customer.name if invoice and invoice.customer else "Cliente"
    total = (
        f"R${float(invoice.total):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if invoice
        else ""
    )
    body = f"Pedido #{order_number}"
    if customer_name:
        body += f" · {customer_name}"
    if total:
        body += f" · {total}"
    return (
        f"Nova venda no {provider}",
        body[:500],
        {
            "type": "sale",
            "provider": order.provider,
            "order_id": order.external_order_id,
            "invoice_id": order.invoice_id or "",
            "route": "/marketplace",
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
    notification = PushNotification(dedupe_key=dedupe_key, title=title, body=body, data=data)
    db.add(notification)
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification


def enqueue_backup_notification(db: Session, filename: str) -> PushNotification | None:
    """Notify once after a backup has been uploaded successfully."""
    dedupe_key = f"backup:{filename}"
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    notification = PushNotification(
        dedupe_key=dedupe_key,
        title="Backup concluído",
        body=f"Cópia do Parts ERP enviada ao Google Drive: {filename}"[:500],
        data={"type": "backup_completed", "filename": filename, "route": "/settings"},
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification


_ORDER_STATUS_LABELS = {
    "paid": "Pagamento aprovado",
    "cancelled": "Pedido cancelado",
    "canceled": "Pedido cancelado",
    "ready_to_ship": "Pronto para envio",
    "shipped": "Despachado",
    "delivered": "Entregue · venda finalizada",
    "returned": "Devolvido",
    "not_delivered": "Não entregue",
    "dropped_off": "Postado",
    "in_hub": "No centro de distribuição",
    "out_for_delivery": "Saiu para entrega",
    "delayed": "Entrega atrasada",
    "unpaid": "Pagamento pendente",
    "to_ship": "Aguardando envio",
    "to_receive": "Aguardando entrega",
    "completed": "Concluído",
    "in_cancel": "Cancelamento em andamento",
    "to_return": "Devolução em andamento",
    "reclined": "Em revisão",
}


def enqueue_order_status_notification(
    db: Session,
    order: MarketplaceOrder,
    previous_status: str | None,
    previous_shipping_status: str | None,
    previous_shipping_substatus: str | None,
) -> PushNotification | None:
    """Notify once when a known order changes payment or delivery state."""
    if previous_status is None:
        return None
    order_changed = previous_status != order.status
    shipping_changed = (
        previous_shipping_status != order.shipping_status
        or previous_shipping_substatus != order.shipping_substatus
    )
    if not order_changed and not shipping_changed:
        return None
    state = (order.status, order.shipping_status, order.shipping_substatus)
    fingerprint = hashlib.sha256(repr(state).encode()).hexdigest()[:20]
    dedupe_key = (
        f"order-status:{order.provider}:{order.seller_id}:{order.external_order_id}:{fingerprint}"
    )
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    provider = "Mercado Livre" if order.provider == "mercadolivre" else "Shopee"
    if shipping_changed and order.shipping_status:
        status = _ORDER_STATUS_LABELS.get(order.shipping_status.lower(), "Envio atualizado")
        if order.shipping_substatus:
            detail = _ORDER_STATUS_LABELS.get(order.shipping_substatus.lower())
            if detail:
                status = f"{status} · {detail}"
        title = f"Rastreio atualizado no {provider}"
    else:
        status = _ORDER_STATUS_LABELS.get(order.status.lower(), "Status do pedido atualizado")
        title = f"Pedido atualizado no {provider}"
    notification = PushNotification(
        dedupe_key=dedupe_key,
        title=title,
        body=f"Pedido #{order.external_order_id}: {status}"[:500],
        data={
            "type": "order_status",
            "provider": order.provider,
            "order_id": order.external_order_id,
            "status": order.status,
            "shipping_status": order.shipping_status or "",
            "shipping_substatus": order.shipping_substatus or "",
            "route": "/marketplace",
        },
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    deliver_pending_notifications(db, only_id=notification.id)
    return notification


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
        if not devices:
            notification.error = "Nenhum celular autorizado para receber notificações"
            continue
        notification.attempts += 1
        try:
            _deliver(credentials, devices, notification)
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


def _deliver(
    credentials: dict[str, Any], devices: list[PushDevice], notification: PushNotification
) -> None:
    """Uses FCM HTTP v1 directly, avoiding heavyweight native dependencies on Termux."""
    access_token = _firebase_access_token(credentials)
    url = f"https://fcm.googleapis.com/v1/projects/{credentials['project_id']}/messages:send"
    headers = {"Authorization": f"Bearer {access_token}"}
    delivered = 0
    failures: list[str] = []
    for device in devices:
        payload = {
            "message": {
                "token": device.token,
                "notification": {"title": notification.title, "body": notification.body},
                "data": {str(key): str(value) for key, value in notification.data.items()},
                "android": {"priority": "HIGH", "notification": {"channel_id": "sales"}},
            }
        }
        response = httpx.post(url, headers=headers, json=payload, timeout=15)
        if response.is_success:
            delivered += 1
            continue
        detail = response.text[:1000]
        failures.append(detail)
        if response.status_code == 404 or "UNREGISTERED" in detail or "INVALID_ARGUMENT" in detail:
            device.active = False
    if not delivered:
        raise RuntimeError("; ".join(failures) or "Firebase recusou a entrega")
