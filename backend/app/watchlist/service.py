"""Watchlist business logic."""

from __future__ import annotations

import asyncio
import logging

from ..db import Database
from ..errors import TickerNotFoundError, WatchlistFullError
from ..market.tickers import validate_ticker
from ..reconcile import TickerReconciler
from .repository import WatchlistRepository

logger = logging.getLogger(__name__)


class WatchlistService:
    """Watchlist reads and mutations, with the tracked-ticker union enforced.

    Every mutation holds a lock across both the database write and the
    reconcile call, so the two can never diverge.
    """

    def __init__(
        self,
        db: Database,
        repo: WatchlistRepository,
        reconciler: TickerReconciler,
        lock: asyncio.Lock,
        cap: int = 25,
    ) -> None:
        self._db = db
        self._repo = repo
        self._reconciler = reconciler
        self._lock = lock
        self._cap = cap

    @property
    def cap(self) -> int:
        return self._cap

    async def list(self) -> list[str]:
        return await self._repo.list()

    async def add(self, raw_ticker: str) -> list[str]:
        ticker = validate_ticker(raw_ticker)
        async with self._lock:
            if await self._repo.contains(ticker):
                return await self._repo.list()
            if await self._repo.count() >= self._cap:
                raise WatchlistFullError(
                    f"Watchlist is limited to {self._cap} tickers. Remove one first."
                )
            async with self._db.transaction():
                await self._repo.add(ticker)
            await self._reconciler.ensure_tracked(ticker)
            return await self._repo.list()

    async def remove(self, raw_ticker: str) -> list[str]:
        """Remove a ticker. Allowed even while holding it (DECISIONS D-02).

        The watchlist row goes; the price feed continues for as long as a
        position remains open, so the position stays valued and visible.
        """
        ticker = validate_ticker(raw_ticker)
        async with self._lock:
            if not await self._repo.contains(ticker):
                raise TickerNotFoundError(f"{ticker} is not on the watchlist.")
            async with self._db.transaction():
                await self._repo.remove(ticker)
            await self._reconciler.release_if_unheld(ticker)
            return await self._repo.list()
