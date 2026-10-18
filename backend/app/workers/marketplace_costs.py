import asyncio
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.integrations.mercadolivre.sync import reconcile_shipping_costs
from app.models import MarketplaceAccount


def _reconcile_marketplace_costs() -> int:
    with SessionLocal() as db:
        accounts = list(
            db.scalars(
                select(MarketplaceAccount).where(
                    MarketplaceAccount.provider == "mercadolivre",
                    MarketplaceAccount.active.is_(True),
                )
            )
        )
        return sum(reconcile_shipping_costs(db, account) for account in accounts)


async def reconcile_marketplace_costs(ctx: dict[str, Any]) -> int:
    del ctx
    return await asyncio.to_thread(_reconcile_marketplace_costs)
