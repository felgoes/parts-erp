from typing import Any

from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.mercadolivre.client import MercadoLivreClient
from app.integrations.mercadolivre.sync import sync_invoice_documents, sync_order
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
            select(MarketplaceAccount).where(MarketplaceAccount.seller_id == seller_id)
        )
        if not account:
            return
        invoice_data = MercadoLivreClient(db, account).get(resource)
        if not isinstance(invoice_data, dict):
            return
        order_ids = invoice_data.get("orders") or [invoice_data.get("order_id")]
        for raw_order_id in order_ids:
            raw_id = raw_order_id.get("id") if isinstance(raw_order_id, dict) else raw_order_id
            order_id = str(raw_id or "")
            order = db.scalar(
                select(MarketplaceOrder).where(MarketplaceOrder.external_order_id == order_id)
            )
            if order and order.invoice_id:
                sync_invoice_documents(db, account, order_id, order.invoice_id)


class WorkerSettings:
    functions = [process_mercadolivre_notification]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 120
    max_tries = 5
