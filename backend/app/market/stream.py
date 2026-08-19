"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

#: Emitted when the cache has not changed, to keep idle proxies from dropping
#: a quiet connection. EventSource ignores comment frames.
_KEEPALIVE_FRAME = ": keepalive\n\n"

#: Seconds without an emitted event before a keepalive comment is sent.
_KEEPALIVE_INTERVAL = 15.0


def create_stream_router(price_cache: PriceCache) -> APIRouter:
    """Build the SSE router bound to this cache.

    Constructed per call rather than at module scope: a shared module-level
    router would accumulate duplicate routes and the first closure's cache
    would win, breaking any fixture that builds more than one app.
    """
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        """Streams every tracked price as one event, at the cache's cadence:

        data: {"AAPL": {"ticker": "AAPL", "price": 190.50, ...}, ...}
        """
        return StreamingResponse(
            _generate_events(price_cache, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
            },
        )

    return router


async def _generate_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
) -> AsyncGenerator[str, None]:
    """Yields SSE frames until the client disconnects."""
    # Tell the client to retry after 1 second if the connection drops.
    yield "retry: 1000\n\n"

    last_version = -1
    last_emit = time.monotonic()
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            emitted = False
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()

                if prices:
                    data = {ticker: update.to_dict() for ticker, update in prices.items()}
                    payload = json.dumps(data)
                    yield f"data: {payload}\n\n"
                    emitted = True

            now = time.monotonic()
            if emitted:
                last_emit = now
            elif now - last_emit >= _KEEPALIVE_INTERVAL:
                yield _KEEPALIVE_FRAME
                last_emit = now

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
