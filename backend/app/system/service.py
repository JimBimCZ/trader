"""Health reporting and the demo reset."""

from __future__ import annotations

import logging

from ..clock import now_ts
from ..config import Settings
from ..db import Database, seed_user
from ..llm.repository import ChatRepository
from ..market import MarketDataSource, PriceCache
from ..portfolio.repository import PositionRepository, SnapshotRepository, TradeRepository
from ..watchlist.repository import WatchlistRepository

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
    """Restores one user's seeded starting state.

    Exists because a demo that auto-executes trades needs a way back to
    $10,000 without deleting the database.
    """

    def __init__(
        self,
        db: Database,
        settings: Settings,
        user_id: str,
        reconciler,
        trade_lock,
        watchlist_lock,
    ) -> None:
        self._db = db
        self._settings = settings
        self._user_id = user_id
        self._positions = PositionRepository(db, user_id)
        self._trades = TradeRepository(db, user_id)
        self._snapshots = SnapshotRepository(db, user_id)
        self._watchlist = WatchlistRepository(db, user_id)
        self._chat = ChatRepository(db, user_id)
        self._reconciler = reconciler
        self._trade_lock = trade_lock
        self._watchlist_lock = watchlist_lock

    async def reset(self) -> None:
        """Wipe this user's state, re-seed them, and reconcile globally."""
        async with self._trade_lock, self._watchlist_lock:
            # Delete and re-seed in ONE transaction: the profile row must
            # never be committed-absent, because every per-user table has a
            # foreign key pointing at it and a concurrent insert landing in
            # that window would fail with a ForeignKeyViolationError.
            # ChatService in particular inserts its user message under
            # neither lock held here, so nothing else serializes it.
            async with self._db.transaction():
                await self._positions.delete_all()
                await self._trades.delete_all()
                await self._snapshots.delete_all()
                await self._chat.delete_all()
                await self._watchlist.delete_all()
                # Updated, not deleted and recreated: deleting the profile
                # cascades the user out of existence and invalidates their
                # cookie, so a reset would silently log them out.
                await self._db.execute(
                    "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                    (self._settings.initial_cash, self._user_id),
                )
                # seed_user writes the t=0 snapshot, so the chart is not
                # empty between here and the writer's next tick.
                await seed_user(self._db, self._settings, self._user_id)

            # Global, not per-user: the tickers this user released may still
            # be watched or held by someone else, and reconcile() is the only
            # thing that checks. It touches the market source rather than the
            # database, so it stays outside the transaction.
            #
            # The price history ring buffer is deliberately left alone. It
            # holds market data per ticker -- shared by everyone, owned by
            # nobody -- so clearing it here blanked every other user's main
            # chart. This user's own chart comes from portfolio_snapshots,
            # which the transaction above already cleared.
            await self._reconciler.reconcile()

        logger.info("Reset %s to seeded state", self._user_id)
