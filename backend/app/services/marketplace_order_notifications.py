"""Status milestone notifications for marketplace orders."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MarketplaceOrder, PushNotification
from app.services.push_notifications import deliver_pending_notifications

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
    """Notify only dispatch handoff/final delivery and attention-worthy states."""
    order_changed = previous_status is not None and previous_status != order.status
    shipping_changed = (
        previous_shipping_status != order.shipping_status
        or previous_shipping_substatus != order.shipping_substatus
    )
    if order.provider == "mercadolivre":
        shipping_status = (order.shipping_status or "").lower()
        shipping_substatus = (order.shipping_substatus or "").lower()
        order_status = order.status.lower()
        problem_states = {"delayed", "not_delivered", "returned"}
        is_cancelled = order_status in {"cancelled", "canceled"} or shipping_status in {
            "cancelled",
            "canceled",
        }
        is_problem = shipping_status in problem_states or shipping_substatus in problem_states
        is_delivered = (
            order_status in {"delivered", "completed"}
            or shipping_status == "delivered"
            or shipping_substatus == "delivered"
        )
        dispatch_states = {"shipped", "dropped_off"}
        handoff_substatuses = {"picked_up", "authorized_by_carrier"}
        is_dispatch_started = (
            shipping_status in dispatch_states
            and (
                previous_shipping_status is None
                or previous_shipping_status.lower() not in dispatch_states
            )
        ) or (
            shipping_status == "ready_to_ship"
            and shipping_substatus in handoff_substatuses
            and (
                previous_shipping_substatus is None
                or previous_shipping_substatus.lower() not in handoff_substatuses
            )
        )
        if not (is_cancelled or is_problem or is_delivered or is_dispatch_started):
            return None
        if previous_status is not None and not order_changed and not shipping_changed:
            return None
        milestone = (
            "cancelled"
            if is_cancelled
            else "problem"
            if is_problem
            else "delivered"
            if is_delivered
            else "dispatch_started"
        )
    elif not order_changed and not shipping_changed:
        return None
    state = (order.status, order.shipping_status, order.shipping_substatus)
    fingerprint = hashlib.sha256(repr(state).encode()).hexdigest()[:20]
    state_key = (
        milestone if order.provider == "mercadolivre" and milestone != "problem" else fingerprint
    )
    dedupe_key = (
        f"order-status:{order.provider}:{order.seller_id}:{order.external_order_id}:{state_key}"
    )
    existing = db.scalar(select(PushNotification).where(PushNotification.dedupe_key == dedupe_key))
    if existing is not None:
        return existing
    provider = "Mercado Livre" if order.provider == "mercadolivre" else "Shopee"
    if order.provider == "mercadolivre" and milestone == "cancelled":
        status, title = "Pedido cancelado", f"Pedido cancelado no {provider}"
    elif order.provider == "mercadolivre" and milestone == "problem":
        status = _ORDER_STATUS_LABELS.get(
            shipping_substatus or shipping_status, "Problema no envio"
        )
        title = "Problema no envio no Mercado Livre"
    elif order.provider == "mercadolivre" and milestone == "dispatch_started":
        status, title = (
            "O pacote foi entregue à rede de envio.",
            "Despacho iniciado no Mercado Livre",
        )
    elif order.provider == "mercadolivre" and milestone == "delivered":
        status, title = "Entrega concluída", "Pedido entregue no Mercado Livre"
    elif shipping_changed and order.shipping_status:
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
        category="order_status",
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
