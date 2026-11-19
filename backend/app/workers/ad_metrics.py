import asyncio
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import MarketplaceAccount
from app.services.ad_performance import sync_ad_metrics_for_account


def _sync_ad_metrics(account_id: str | None = None) -> dict[str, int]:
    updated = errors = 0
    with SessionLocal() as db:
        query = select(MarketplaceAccount).where(
            MarketplaceAccount.active.is_(True), MarketplaceAccount.provider == "mercadolivre"
        )
        if account_id:
            query = query.where(MarketplaceAccount.id == account_id)
        accounts = list(db.scalars(query))
        for account in accounts:
            result = sync_ad_metrics_for_account(db, account.id)
            updated += result["updated"]
            errors += result["errors"]
    return {"updated": updated, "errors": errors}


async def sync_mercadolivre_ad_metrics(
    ctx: dict[str, Any], account_id: str | None = None
) -> dict[str, int]:
    del ctx
    return await asyncio.to_thread(_sync_ad_metrics, account_id)
