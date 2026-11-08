import asyncio
from typing import Any

from arq import cron

from app.db.session import SessionLocal
from app.services.vehicle_fleet_import import import_latest_fleet_job
from app.services.vehicle_market_live import sync_live_vehicle_market


async def refresh_vehicle_market_fleet(ctx: dict[str, Any]) -> dict[str, Any]:
    del ctx
    return await asyncio.to_thread(import_latest_fleet_job)


def _refresh_registrations() -> dict[str, Any]:
    with SessionLocal() as db:
        return sync_live_vehicle_market(db)


async def refresh_vehicle_registrations(ctx: dict[str, Any]) -> dict[str, Any]:
    del ctx
    result = await asyncio.to_thread(_refresh_registrations)
    return {key: result.get(key) for key in ("status", "period")}


vehicle_market_cron_jobs = [
    cron(
        refresh_vehicle_market_fleet,
        name="refresh-vehicle-market-fleet",
        hour=6,
        minute=20,
        timeout=1800,
        max_tries=2,
        run_at_startup=True,
    ),
    cron(
        refresh_vehicle_registrations,
        name="refresh-vehicle-registrations",
        hour={0, 6, 12, 18},
        minute=35,
        run_at_startup=True,
    ),
]
