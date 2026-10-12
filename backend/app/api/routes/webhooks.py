"""Webhooks dos marketplaces.

Módulo próprio porque aqui a regra de segurança é outra: a rota é anônima, então o payload é
validado por forma, o tamanho é limitado, a frequência é limitada por IP e por provedor, e
notificação repetida não entra duas vezes na fila. O worker nunca confia no payload: ele
reconsulta o pedido no provedor com a credencial da conta.
"""

import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.queue import get_queue_pool
from app.core.request_security import (
    client_ip,
    enforce_rate_limit,
    read_json_object,
    remember_once,
)
from app.db.session import get_db
from app.models import MarketplaceAccount

router = APIRouter(prefix="/integrations/mercadolivre", tags=["Mercado Livre"])
shopee_router = APIRouter(prefix="/integrations/shopee", tags=["Shopee"])
logger = logging.getLogger(__name__)

WEBHOOK_MAX_BYTES = 16 * 1024
WEBHOOK_IP_LIMIT_PER_MINUTE = 120
WEBHOOK_PROVIDER_LIMIT_PER_MINUTE = 600
WEBHOOK_DEDUP_SECONDS = 60
WEBHOOK_BUSY = "Muitas notificações agora; tente novamente em instantes"

ML_TOPICS = {"orders_v2", "shipments", "payments", "invoices", "claims", "returns"}


@router.post("/webhook", status_code=202)
@router.post("/notifications", status_code=202)
async def mercadolivre_webhook(request: Request) -> dict[str, bool]:
    payload = await read_json_object(request, WEBHOOK_MAX_BYTES)
    _enforce_webhook_limits(request, "mercadolivre")
    topic = str(payload.get("topic", ""))
    resource = str(payload.get("resource", ""))
    seller_id = str(payload.get("user_id", ""))
    _validate_mercadolivre_notification(topic, resource, seller_id)
    if not remember_once(
        f"webhook:mercadolivre:{topic}:{resource}:{seller_id}", WEBHOOK_DEDUP_SECONDS
    ):
        return {"accepted": True}
    received_at = time.monotonic()
    queue = await get_queue_pool()
    job = await queue.enqueue_job("process_mercadolivre_notification", topic, resource, seller_id)
    logger.info(
        "webhook accepted provider=mercadolivre topic=%s resource=%s seller_id=%s "
        "queue_ms=%.1f job_id=%s",
        topic,
        resource,
        seller_id,
        (time.monotonic() - received_at) * 1000,
        getattr(job, "job_id", "unknown"),
    )
    return {"accepted": True}


@shopee_router.post("/webhook", status_code=202)
async def shopee_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    payload = await read_json_object(request, WEBHOOK_MAX_BYTES)
    _enforce_webhook_limits(request, "shopee")
    shop_id = str(payload.get("shop_id") or payload.get("shopid") or "")
    if not shop_id:
        raise HTTPException(status_code=400, detail="Loja Shopee ausente")
    # Loja desconhecida não entra na fila (evita inundação), mas a resposta é a mesma de
    # sucesso para não virar oráculo de "esta loja está conectada?".
    known_shop = db.scalar(
        select(MarketplaceAccount.id).where(
            MarketplaceAccount.provider == "shopee",
            MarketplaceAccount.seller_id == shop_id,
            MarketplaceAccount.active.is_(True),
        )
    )
    if known_shop is None:
        logger.info("webhook ignored provider=shopee shop_id nao conectado")
        return {"accepted": True}
    order_sn = str((payload.get("data") or {}).get("ordersn") or payload.get("ordersn") or "")
    if not remember_once(f"webhook:shopee:{shop_id}:{order_sn}", WEBHOOK_DEDUP_SECONDS):
        return {"accepted": True}
    received_at = time.monotonic()
    queue = await get_queue_pool()
    job = await queue.enqueue_job("process_shopee_notification", payload)
    logger.info(
        "webhook accepted provider=shopee shop_id=%s order_sn=%s queue_ms=%.1f job_id=%s",
        shop_id,
        order_sn,
        (time.monotonic() - received_at) * 1000,
        getattr(job, "job_id", "unknown"),
    )
    return {"accepted": True}


def _enforce_webhook_limits(request: Request, provider: str) -> None:
    ip = client_ip(request)
    enforce_rate_limit(
        f"webhook:{provider}:ip:{ip}", WEBHOOK_IP_LIMIT_PER_MINUTE, detail=WEBHOOK_BUSY
    )
    enforce_rate_limit(
        f"webhook:{provider}:provider", WEBHOOK_PROVIDER_LIMIT_PER_MINUTE, detail=WEBHOOK_BUSY
    )


def _validate_mercadolivre_notification(topic: str, resource: str, seller_id: str) -> None:
    if topic not in ML_TOPICS or not resource.startswith("/") or not seller_id.isdigit():
        raise HTTPException(status_code=400, detail="Notificação inválida")
    if topic == "orders_v2":
        valid = bool(re.fullmatch(r"/orders/\d+", resource))
    elif topic == "invoices":
        valid = resource.startswith(f"/users/{seller_id}/invoices/")
    else:
        valid = bool(re.fullmatch(r"/(shipments|collections|claims|returns)/\d+", resource))
    if not valid:
        raise HTTPException(status_code=400, detail="Recurso de notificação inválido")
