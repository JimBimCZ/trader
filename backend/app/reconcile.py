"""Keeps the market data source's tracked tickers in sync with the database.

The rule (DECISIONS D-01): the price source tracks
`union(watchlist tickers, tickers with a non-zero position)`.

This module is the only place allowed to call `source.remove_ticker()`,
because that call also evicts the cached price. Removing a ticker the user
still holds would make its price `None`, and portfolio valuation would then
fail — or worse, silently value the position at zero.
"""

from __future__ import annotations

import logging

from .market import MarketDataSource
from .portfolio.repository import PositionRepository
from .watchlist.repository import WatchlistRepository

logger = logging.getLogger(__name__)


class TickerReconciler:
    """Owns the tracked-ticker set."""

    def __init__(
        self,
        source: MarketDataSource,
        watchlist_repo: WatchlistRepository,
        position_repo: PositionRepository,
    ) -> None:
        self._source = source
        self._watchlist = watchlist_repo
        self._positions = position_repo

    async def compute_tracked_tickers(self) -> list[str]:
        """The union of watched tickers and tickers with an open position."""
        watched = await self._watchlist.list()
        held = await self._positions.list_open_tickers()
        return sorted(set(watched) | set(held))

    async def ensure_tracked(self, ticker: str) -> None:
        """Start tracking a ticker if it is not already tracked. Idempotent."""
        if ticker not in self._source.get_tickers():
            await self._source.add_ticker(ticker)
            logger.info("Now tracking %s", ticker)

    async def release_if_unheld(self, ticker: str) -> None:
        """Stop tracking a ticker, but only if no position remains open.

        This is the single enforcement point for DECISIONS D-03.
        """
        position = await self._positions.get(ticker)
        if position is not None and position.quantity > 0:
            logger.info("Keeping %s tracked: position still open", ticker)
            return
        await self._source.remove_ticker(ticker)
        logger.info("Stopped tracking %s", ticker)

    async def reconcile(self) -> list[str]:
        """Force the source's tracked set to match the union exactly.

        Used at startup and after a reset, where the source may be tracking
        anything at all.
        """
        target = set(await self.compute_tracked_tickers())
        current = set(self._source.get_tickers())

        for ticker in sorted(target - current):
            await self._source.add_ticker(ticker)
        for ticker in sorted(current - target):
            await self._source.remove_ticker(ticker)

        return sorted(target)
