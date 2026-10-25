import asyncio
from typing import Any

from app.services.vehicle_fleet_import import import_latest_fleet_job


async def refresh_vehicle_market_fleet(ctx: dict[str, Any]) -> dict[str, Any]:
    del ctx
    return await asyncio.to_thread(import_latest_fleet_job)
