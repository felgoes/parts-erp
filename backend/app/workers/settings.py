import asyncio
from datetime import datetime
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.sync import (
    extract_invoice_order_ids,
    retry_due_orders,
    retry_pending_automations,
    sync_all,
    sync_invoice_documents,
    sync_order,
)
from app.integrations.shopee.sync import sync_all as sync_shopee_all
from app.integrations.shopee.sync import sync_order as sync_shopee_order
from app.models import MarketplaceAccount, MarketplaceOrder, MarketplaceOrderEvent
from app.services.after_sale import after_sale_notification, upsert_after_sale_case
from app.services.push_notifications import deliver_pending_notifications, enqueue_sale_notification


def _process_mercadolivre_notification(
    topic: str, resource: str, seller_id: str
) -> None:
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(MarketplaceAccount.seller_id == seller_id)
        )
        if not account:
            return
        data = MercadoLivreClient(db, account).get(resource)
        if not isinstance(data, dict):
            return
        order_ids = extract_invoice_order_ids(data)
        if topic == "orders_v2":
            order_ids.add(resource.rsplit("/", 1)[-1])
        for key in ("order_id", "order_ids", "related_order_id", "related_orders"):
            value = data.get(key)
            values = value if isinstance(value, list) else [value]
            for candidate in values:
                raw = candidate.get("id") if isinstance(candidate, dict) else candidate
                if raw:
                    order_ids.add(str(raw))
        related_entities = data.get("related_entities")
        if isinstance(related_entities, list):
            for entity in related_entities:
                if not isinstance(entity, dict):
                    continue
                if "order" not in str(entity.get("type", "")).lower():
                    continue
                raw = entity.get("id")
                if raw:
                    order_ids.add(str(raw).rsplit("/", 1)[-1])
        # Shipment webhooks identify the shipment, not always its sale. Resolve
        # the shipment against our persisted link so dispatch/delivery events
        # update the same order and invoice as the original sale webhook.
        if topic == "shipments":
            shipment_id = str(data.get("id") or resource.rsplit("/", 1)[-1])
            linked_orders = db.scalars(
                select(MarketplaceOrder).where(
                    MarketplaceOrder.provider == "mercadolivre",
                    MarketplaceOrder.seller_id == seller_id,
                    MarketplaceOrder.shipment_id == shipment_id,
                )
            )
            linked_orders = list(linked_orders)
            order_ids.update(order.external_order_id for order in linked_orders)
            if not linked_orders:
                # The current Shipments contract no longer returns order_id.
                # Resolve associations through the official shipment-orders endpoint.
                try:
                    related = MercadoLivreClient(db, account).get(
                        f"/shipments/{shipment_id}/orders",
                        extra_headers={"x-new-domain": "true"},
                    )
                except MercadoLivreError:
                    related = []
                related_rows = (
                    related
                    if isinstance(related, list)
                    else (related.get("results", []) if isinstance(related, dict) else [])
                )
                for row in related_rows:
                    if isinstance(row, dict) and row.get("order_id"):
                        order_ids.add(str(row["order_id"]))
        for raw_order_id in order_ids:
            order_id = str(raw_order_id or "")
            if not order_id:
                continue
            previous_order = db.scalar(
                select(MarketplaceOrder).where(
                    MarketplaceOrder.provider == "mercadolivre",
                    MarketplaceOrder.seller_id == seller_id,
                    MarketplaceOrder.external_order_id == order_id,
                )
            )
            previous_invoice_id = previous_order.invoice_id if previous_order else None
            # Always refresh the order before processing its webhook. Existing
            # invoices must also receive cancellations, refunds and returns.
            order = sync_order(db, seller_id, f"/orders/{order_id}")
            # A sale alert is emitted exactly once, only when this webhook first
            # turns a marketplace order into a linked ERP invoice.
            if order and order.invoice_id and not previous_invoice_id:
                enqueue_sale_notification(db, order)
            if topic in {"claims", "returns"} and order:
                event_data = after_sale_notification(topic, data)
                case_id = str(event_data.get("id") or resource.rsplit("/", 1)[-1])[:100]
                saved_events = (order.payload or {}).get("_erp_after_sale_events", [])
                if not isinstance(saved_events, list):
                    saved_events = []
                fingerprint = (
                    event_data.get("kind"),
                    event_data.get("id"),
                    event_data.get("status"),
                )
                exists = any(
                    isinstance(item, dict)
                    and (item.get("kind"), item.get("id"), item.get("status")) == fingerprint
                    for item in saved_events
                )
                if not exists:
                    order.payload = {
                        **(order.payload if isinstance(order.payload, dict) else {}),
                        "_erp_after_sale_events": [*saved_events, event_data][-50:],
                    }
                    event_date = datetime.fromisoformat(
                        event_data["created_at"].replace("Z", "+00:00")
                    )
                    db.add(
                        MarketplaceOrderEvent(
                            order_id=order.id,
                            event_type="after_sale",
                            status=str(event_data["status"]),
                            detail=event_data.get("reason"),
                            payload={
                                key: value for key, value in event_data.items() if value is not None
                            },
                            created_at=event_date,
                        )
                    )
                upsert_after_sale_case(db, order, event_data, data, case_id)
                db.commit()
            if order.invoice_id and topic == "invoices":
                sync_invoice_documents(db, account, order_id, order.invoice_id)


async def process_mercadolivre_notification(
    ctx: dict[str, Any], topic: str, resource: str, seller_id: str
) -> None:
    del ctx
    await asyncio.to_thread(_process_mercadolivre_notification, topic, resource, seller_id)


def _sync_mercadolivre_account(seller_id: str) -> None:
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.active.is_(True),
            )
        )
        if account:
            sync_all(db, account)


async def sync_mercadolivre_account(ctx: dict[str, Any], seller_id: str) -> None:
    del ctx
    await asyncio.to_thread(_sync_mercadolivre_account, seller_id)


def _sync_shopee_account(shop_id: str) -> None:
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "shopee",
                MarketplaceAccount.seller_id == str(shop_id),
                MarketplaceAccount.active.is_(True),
            )
        )
        if account:
            sync_shopee_all(db, account)


async def sync_shopee_account(ctx: dict[str, Any], shop_id: str) -> None:
    del ctx
    await asyncio.to_thread(_sync_shopee_account, shop_id)


def _process_shopee_notification(payload: dict[str, Any]) -> None:
    shop_id = str(payload.get("shop_id") or payload.get("shopid") or "")
    order_sn = str((payload.get("data") or {}).get("ordersn") or payload.get("ordersn") or "")
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "shopee",
                MarketplaceAccount.seller_id == shop_id,
                MarketplaceAccount.active.is_(True),
            )
        )
        if not account:
            return
        if order_sn:
            previous_order = db.scalar(
                select(MarketplaceOrder).where(
                    MarketplaceOrder.provider == "shopee",
                    MarketplaceOrder.seller_id == shop_id,
                    MarketplaceOrder.external_order_id == order_sn,
                )
            )
            previous_invoice_id = previous_order.invoice_id if previous_order else None
            order = sync_shopee_order(db, account, order_sn)
            if order and order.invoice_id and not previous_invoice_id:
                enqueue_sale_notification(db, order)
        else:
            sync_shopee_all(db, account)


async def process_shopee_notification(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    del ctx
    await asyncio.to_thread(_process_shopee_notification, payload)


def _reconcile_pending_marketplace_documents() -> int:
    with SessionLocal() as db:
        return retry_pending_automations(db)


async def reconcile_pending_marketplace_documents(ctx: dict[str, Any]) -> int:
    del ctx
    return await asyncio.to_thread(_reconcile_pending_marketplace_documents)


def _retry_due_mercadolivre_orders() -> int:
    with SessionLocal() as db:
        return retry_due_orders(db)


async def retry_due_mercadolivre_orders(ctx: dict[str, Any]) -> int:
    del ctx
    return await asyncio.to_thread(_retry_due_mercadolivre_orders)


def _retry_pending_push_notifications() -> int:
    with SessionLocal() as db:
        return deliver_pending_notifications(db)


async def retry_pending_push_notifications(ctx: dict[str, Any]) -> int:
    del ctx
    return await asyncio.to_thread(_retry_pending_push_notifications)


class WorkerSettings:
    functions = [
        process_mercadolivre_notification,
        sync_mercadolivre_account,
        sync_shopee_account,
        process_shopee_notification,
        retry_due_mercadolivre_orders,
        retry_pending_push_notifications,
    ]
    cron_jobs = [
        cron(
            reconcile_pending_marketplace_documents,
            name="reconcile-pending-marketplace-documents",
            minute=set(range(60)),
            second=0,
        ),
        cron(
            retry_due_mercadolivre_orders,
            name="retry-failed-mercadolivre-orders",
            minute=set(range(60)),
            second=15,
        ),
        cron(
            retry_pending_push_notifications,
            name="retry-pending-push-notifications",
            minute=set(range(60)),
            second=30,
        ),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 120
    max_tries = 5
