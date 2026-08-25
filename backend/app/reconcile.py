"""Keeps the market data source's tracked tickers in sync with the database.

The rule (DECISIONS D-01): the price source tracks
`union(watchlist tickers, tickers with a non-zero position)` -- across every
user, not just whoever happens to be making the request.

This module is the only place allowed to call `source.remove_ticker()`,
because that call also evicts the cached price. Removing a ticker that any
user still holds would make its price `None`, and that user's portfolio
valuation would then fail -- or worse, silently value the position at zero.
"""

from __future__ import annotations

import logging

from .db import DEFAULT_WATCHLIST, Database
from .errors import MarketCapacityFullError
from .market import MarketDataSource
from .portfolio.models import EPSILON

logger = logging.getLogger(__name__)


class TickerReconciler:
    """Owns the tracked-ticker set, globally.

    Both sides are global by necessity. The tracked set feeds one shared price
    cache, so "should we track this?" and "may we stop?" are questions about
    every user at once, not about whoever happens to be making the request.
    """

    def __init__(self, source: MarketDataSource, db: Database, capacity: int) -> None:
        self._source = source
        self._db = db
        self._capacity = capacity

    async def compute_tracked_tickers(self) -> list[str]:
        """Every watched ticker and every held ticker, across all users.

        Expired guests are deleted rows, so they drop out of this query on
        their own -- no liveness filter is needed.

        With nobody in the database the union is empty, which would leave the
        feed dark: a fresh deployment tracks nothing, reports `degraded`, and
        hands the first visitor a watchlist with no prices in it. The default
        watchlist is the floor instead -- it is exactly what the next minted
        guest will be seeded with, so keeping it warm is keeping the app
        ready rather than tracking something speculative.
        """
        rows = await self._db.fetch_all(
            "SELECT DISTINCT ticker FROM watchlist "
            "UNION "
            "SELECT DISTINCT ticker FROM positions WHERE quantity > ?",
            (EPSILON,),
        )
        return sorted(row["ticker"] for row in rows) or sorted(DEFAULT_WATCHLIST)

    async def ensure_tracked(self, ticker: str) -> None:
        """Start tracking a ticker if it is not already. Idempotent."""
        if ticker in self._source.get_tickers():
            return
        if len(self._source.get_tickers()) >= self._capacity:
            raise MarketCapacityFullError(
                f"The market data feed is tracking its maximum of {self._capacity} "
                f"tickers. Remove one from a watchlist before adding another."
            )
        await self._source.add_ticker(ticker)
        logger.info("Now tracking %s", ticker)

    async def release_if_unheld(self, ticker: str) -> None:
        """Stop tracking only when the ticker is not in the target set.

        Removing a ticker also evicts its cached price, so releasing one that
        another user still holds makes their valuation fail -- or worse,
        silently value the position at zero.

        Asks `compute_tracked_tickers()` rather than running its own
        "does anyone watch or hold this?" query, so the default-watchlist
        floor lives in exactly one place. With its own query it applied only
        the raw union, and the last user to empty their watchlist could drain
        the tracked set to nothing: the price cache went empty process-wide,
        every later visitor was seeded with ten tickers that had no prices,
        and health reported `degraded` until a restart.
        """
        if ticker in await self.compute_tracked_tickers():
            logger.info(
                "Keeping %s tracked: another user watches or holds it, "
                "or it is part of the default floor",
                ticker,
            )
            return
        await self._source.remove_ticker(ticker)
        logger.info("Stopped tracking %s", ticker)

    async def reconcile(self) -> list[str]:
        """Force the source's tracked set to match the global union exactly.

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
