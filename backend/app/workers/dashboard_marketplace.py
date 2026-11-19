import asyncio
from datetime import date
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import MarketplaceAccount
from app.services.dashboard_marketplace_sync import sync_dashboard_orders_for_period


def _sync_dashboard_marketplace_orders(account_id: str, start_date: str, end_date: str) -> int:
    with SessionLocal() as db:
        account = db.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.id == account_id,
                MarketplaceAccount.provider == "mercadolivre",
                MarketplaceAccount.active.is_(True),
            )
        )
        if not account:
            return 0
        return sync_dashboard_orders_for_period(
            db, account, date.fromisoformat(start_date), date.fromisoformat(end_date)
        )


async def sync_dashboard_marketplace_orders(
    ctx: dict[str, Any], account_id: str, start_date: str, end_date: str
) -> int:
    del ctx
    return await asyncio.to_thread(
        _sync_dashboard_marketplace_orders, account_id, start_date, end_date
    )
