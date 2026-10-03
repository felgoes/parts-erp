from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.integrations.mercadolivre.sync import (
    automate_order_documents,
    extract_invoice_order_ids,
    retry_due_orders,
    retry_pending_automations,
    sync_all,
    sync_order,
)
from app.integrations.shopee.sync import sync_all as sync_shopee_all
from app.integrations.shopee.sync import sync_order as sync_shopee_order
from app.models import MarketplaceAccount, MarketplaceOrder


async def process_mercadolivre_notification(
    ctx: dict[str, Any], topic: str, resource: str, seller_id: str
) -> None:
    del ctx
    with SessionLocal() as db:
        if topic == "orders_v2":
            sync_order(db, seller_id, resource)
            return

        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "mercadolivre",
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.active.is_(True),
            )
        )
        if not account:
            return
        invoice_data = MercadoLivreClient(db, account).get(resource)
        if not isinstance(invoice_data, dict):
            return
        for order_id in extract_invoice_order_ids(invoice_data):
            order = db.scalar(
                select(MarketplaceOrder).where(
                    MarketplaceOrder.provider == "mercadolivre",
                    MarketplaceOrder.external_order_id == order_id,
                )
            )
            if not order or not order.invoice_id:
                order = sync_order(db, seller_id, f"/orders/{order_id}")
            if order.invoice_id:
                automate_order_documents(db, order, account)


async def sync_mercadolivre_account(ctx: dict[str, Any], seller_id: str) -> None:
    del ctx
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.provider == "mercadolivre",
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.active.is_(True),
            )
        )
        if account:
            sync_all(db, account)


async def retry_mercadolivre_automations(ctx: dict[str, Any]) -> None:
    del ctx
    with SessionLocal() as db:
        retry_pending_automations(db)


async def retry_mercadolivre_orders(ctx: dict[str, Any]) -> None:
    del ctx
    with SessionLocal() as db:
        retry_due_orders(db)


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


class WorkerSettings:
    functions = [
        process_mercadolivre_notification,
        sync_mercadolivre_account,
        retry_mercadolivre_automations,
        retry_mercadolivre_orders,
        sync_shopee_account,
        process_shopee_notification,
    ]
    cron_jobs = [
        cron(retry_mercadolivre_automations, second=15),
        cron(retry_mercadolivre_orders, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 120
    max_tries = 5
