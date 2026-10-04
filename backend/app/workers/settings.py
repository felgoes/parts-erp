from typing import Any

from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.integrations.mercadolivre.sync import (
    automate_order_documents,
    extract_invoice_order_ids,
    sync_all,
    sync_invoice_documents,
    sync_order,
)
from app.integrations.shopee.sync import sync_all as sync_shopee_all, sync_order as sync_shopee_order
from app.models import MarketplaceAccount, MarketplaceOrder


async def process_mercadolivre_notification(
    ctx: dict[str, Any], topic: str, resource: str, seller_id: str
) -> None:
    del ctx
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
        for raw_order_id in order_ids:
            order_id = str(raw_order_id or "")
            if not order_id:
                continue
            order = db.scalar(
                select(MarketplaceOrder).where(MarketplaceOrder.external_order_id == order_id)
            )
            if not order or not order.invoice_id:
                order = sync_order(db, seller_id, f"/orders/{order_id}")
            if order.invoice_id:
                if topic == "invoices":
                    sync_invoice_documents(db, account, order_id, order.invoice_id)
                else:
                    automate_order_documents(db, order)


class WorkerSettings:
    functions = [process_mercadolivre_notification, sync_mercadolivre_account, sync_shopee_account, process_shopee_notification]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 120
    max_tries = 5


async def sync_mercadolivre_account(ctx: dict[str, Any], seller_id: str) -> None:
    del ctx
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.active.is_(True),
            )
        )
        if account:
            sync_all(db, account)


async def sync_shopee_account(ctx: dict[str, Any], shop_id: str) -> None:
    del ctx
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


async def process_shopee_notification(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    del ctx
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
            sync_shopee_order(db, account, order_sn)
        else:
            sync_shopee_all(db, account)
