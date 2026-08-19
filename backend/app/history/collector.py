"""Background task that copies price ticks into the history ring buffer."""

from __future__ import annotations

import asyncio
import logging

from ..market import PriceCache
from .buffer import HistoryStore

logger = logging.getLogger(__name__)


class HistoryCollector:
    """Polls the price cache and appends changed prices to the history store.

    Mirrors the SSE generator's version-check approach rather than adding a
    callback to PriceCache, keeping the shipped market module untouched.
    """

    def __init__(self, price_cache: PriceCache, store: HistoryStore, interval: float = 0.5) -> None:
        self._cache = price_cache
        self._store = store
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Begin collecting. Seeds from whatever the cache already holds."""
        self._collect_once()
        self._task = asyncio.create_task(self._run_loop(), name="history-collector")
        logger.info("History collector started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("History collector stopped")

    def _collect_once(self) -> None:
        for ticker, update in self._cache.get_all().items():
            self._store.append(ticker, update.timestamp, update.price)

    async def _run_loop(self) -> None:
        last_version = -1
        while True:
            try:
                version = self._cache.version
                if version != last_version:
                    self._collect_once()
                    # Advance only after a successful collect, so a transient
                    # failure is retried on the next poll instead of being
                    # skipped permanently.
                    last_version = version
            except Exception:
                logger.exception("History collection failed")
            await asyncio.sleep(self._interval)
