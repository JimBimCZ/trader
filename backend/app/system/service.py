"""Health reporting and the demo reset."""

from __future__ import annotations

import logging

from ..clock import now_ts
from ..config import Settings
from ..db import Database, seed_if_empty
from ..market import MarketDataSource, PriceCache

logger = logging.getLogger(__name__)


async def health_status(
    db: Database,
    price_cache: PriceCache,
    source: MarketDataSource,
    settings: Settings,
) -> dict:
    """Readiness detail. E2E waits on this rather than sleeping."""
    db_ok = await db.is_healthy()

    prices = price_cache.get_all()
    if prices:
        newest = max(update.timestamp for update in prices.values())
        seconds_since_last_tick = round(max(0.0, now_ts() - newest), 3)
    else:
        seconds_since_last_tick = None

    # Stale or absent prices mean the UI is showing nothing useful, even
    # though the process is up.
    ticking = seconds_since_last_tick is not None and seconds_since_last_tick < 30
    status = "ok" if db_ok and ticking else "degraded"

    return {
        "status": status,
        "market_source": settings.market_source_name,
        "seconds_since_last_tick": seconds_since_last_tick,
        "tracked_tickers": len(source.get_tickers()),
        "db_ok": db_ok,
    }


class ResetService:
    """Restores the seeded starting state.

    Exists because a demo that auto-executes trades needs a way back to
    $10,000 without deleting the database file.
    """

    def __init__(
        self,
        db: Database,
        settings: Settings,
        users,
        positions,
        trades,
        snapshots,
        watchlist_repo,
        chat_repo,
        reconciler,
        history_store,
        trade_lock,
        watchlist_lock,
    ) -> None:
        self._db = db
        self._settings = settings
        self._users = users
        self._positions = positions
        self._trades = trades
        self._snapshots = snapshots
        self._watchlist = watchlist_repo
        self._chat = chat_repo
        self._reconciler = reconciler
        self._history = history_store
        self._trade_lock = trade_lock
        self._watchlist_lock = watchlist_lock

    async def reset(self) -> None:
        """Wipe user state, re-seed, and resync the tracked-ticker set."""
        async with self._trade_lock, self._watchlist_lock:
            async with self._db.transaction():
                await self._positions.delete_all()
                await self._trades.delete_all()
                await self._snapshots.delete_all()
                await self._chat.delete_all()
                await self._watchlist.delete_all()
                await self._db.execute("DELETE FROM users_profile WHERE id = 'default'")

            await seed_if_empty(self._db, self._settings)
            await self._reconciler.reconcile()
            self._history.clear()

            async with self._db.transaction():
                await self._snapshots.insert(self._settings.initial_cash)

        logger.info("Reset to seeded state")
