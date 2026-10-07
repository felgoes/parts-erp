"""Authenticated stream of committed ERP changes."""

from collections.abc import AsyncGenerator

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models import User

router = APIRouter(prefix="/events", tags=["Atualizações"])
CHANNEL = "parts-erp:changes"


@router.get("/stream")
async def stream_changes(
    request: Request, _user: User = Depends(get_current_user)
) -> StreamingResponse:
    async def events() -> AsyncGenerator[str, None]:
        connection = redis.from_url(get_settings().redis_url, decode_responses=True)
        subscription = connection.pubsub()
        try:
            await subscription.subscribe(CHANNEL)
            yield "event: ready\ndata: {}\n\n"
            while not await request.is_disconnected():
                message = await subscription.get_message(
                    ignore_subscribe_messages=True, timeout=15.0
                )
                if message is not None:
                    yield "event: update\ndata: {}\n\n"
                else:
                    yield ": keepalive\n\n"
        finally:
            await subscription.aclose()
            await connection.aclose()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
