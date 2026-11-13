import asyncio
import re
from datetime import date
from typing import Any

import httpx
from arq import Retry, cron
from sqlalchemy import select

from app.db.session import SessionLocal
from app.integrations.mercadolivre.client import MercadoLivreClient, MercadoLivreError
from app.integrations.mercadolivre.full_sync import (
    refresh_full_stock,
    sync_full_account,
    upsert_full_operation,
)
from app.models import FullInventory, MarketplaceAccount


def _active_full_account_ids(account_id: str | None = None) -> list[str]:
    with SessionLocal() as db:
        query = select(MarketplaceAccount.id).where(
            MarketplaceAccount.active.is_(True),
            MarketplaceAccount.provider == "mercadolivre",
        )
        if account_id:
            query = query.where(MarketplaceAccount.id == account_id)
        return list(db.scalars(query))


def _add_counts(result: dict[str, int], current: dict[str, int]) -> None:
    for key in result:
        result[key] += current.get(key, 0)


def _full_account_id_for_seller(seller_id: str) -> str | None:
    with SessionLocal() as db:
        return db.scalar(
            select(MarketplaceAccount.id).where(
                MarketplaceAccount.provider == "mercadolivre",
                MarketplaceAccount.active.is_(True),
                MarketplaceAccount.seller_id == seller_id,
            )
        )


def _refresh_from_notification(account_id: str, resource: str) -> None:
    with SessionLocal() as db:
        account = db.get(MarketplaceAccount, account_id)
        if not account or not account.active or account.provider != "mercadolivre":
            return
        client = MercadoLivreClient(db, account)
        event = client.get(resource)
        if (
            not isinstance(event, dict)
            or str(event.get("id")) != resource.rsplit("/", 1)[-1]
            or str(event.get("seller_id")) != account.seller_id
        ):
            return
        inventory_id = str(event.get("inventory_id") or event.get("seller_product_id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", inventory_id):
            raise ValueError("Identificador de inventário Full inválido")
        inventory = db.scalar(
            select(FullInventory).where(
                FullInventory.account_id == account.id,
                FullInventory.inventory_id == inventory_id,
            )
        )
        if inventory is None:
            inventory = FullInventory(account_id=account.id, inventory_id=inventory_id)
            db.add(inventory)
            db.flush()
        refresh_full_stock(client, inventory)
        upsert_full_operation(db, account, inventory, event)
        db.commit()


async def process_full_stock_notification(
    ctx: dict[str, Any], resource: str, seller_id: str
) -> None:
    account_id = await asyncio.to_thread(_full_account_id_for_seller, seller_id)
    if not account_id:
        return
    redis = ctx.get("redis")
    lock = redis.lock(f"marketplace-full-sync:{account_id}", timeout=7200) if redis else None
    attempt = ctx.get("job_try", 1)
    if lock is not None and not await lock.acquire(blocking=False):
        raise Retry(defer=min(30 * attempt, 120))
    try:
        await asyncio.to_thread(_refresh_from_notification, account_id, resource)
    except httpx.TransportError as exc:
        raise Retry(defer=min(15 * 2 ** (attempt - 1), 120)) from exc
    except MercadoLivreError as exc:
        status = exc.status_code
        if status is None or status in {404, 429} or status >= 500:
            raise Retry(defer=min(15 * 2 ** (attempt - 1), 120)) from exc
        raise
    finally:
        if lock is not None:
            await lock.release()


async def sync_mercadolivre_full(
    ctx: dict[str, Any],
    account_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, int]:
    result = {"inventories": 0, "operations": 0, "errors": 0}
    start = date.fromisoformat(date_from) if date_from else None
    end = date.fromisoformat(date_to) if date_to else None
    redis = ctx.get("redis")
    for current_id in _active_full_account_ids(account_id):
        lock = redis.lock(f"marketplace-full-sync:{current_id}", timeout=7200) if redis else None
        if lock is not None and not await lock.acquire(blocking=False):
            continue
        try:
            current = await asyncio.to_thread(sync_full_account, current_id, start, end)
            _add_counts(result, current)
        finally:
            if lock is not None:
                await lock.release()
    return result


marketplace_full_cron_jobs = [
    cron(sync_mercadolivre_full, name="sync-mercadolivre-full", minute={0, 30}, second=40)
]
