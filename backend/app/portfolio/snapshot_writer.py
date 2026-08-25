"""Background task recording portfolio value over time."""

from __future__ import annotations

import asyncio
import logging

from ..clock import iso_seconds_ago
from ..config import Settings
from ..db import Database
from ..identity import UserStore
from ..market import PriceCache
from .service import build_trade_service

logger = logging.getLogger(__name__)


class SnapshotWriter:
    """Writes a portfolio snapshot per active user on an interval.

    Builds its own per-user services rather than receiving one: there is no
    single user at startup any more, and the set changes between ticks.
    """

    def __init__(
        self,
        db: Database,
        settings: Settings,
        user_store: UserStore,
        price_cache: PriceCache,
        interval: float = 30.0,
        retention_days: int = 7,
    ) -> None:
        self._db = db
        self._settings = settings
        self._users = user_store
        self._price_cache = price_cache
        self._interval = interval
        self._retention_days = retention_days
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Write immediately, then start the periodic task.

        The immediate write means a returning user's P&L chart has a point at
        t=0 rather than being empty for the first interval.
        """
        await self.write_for_active_users()
        self._task = asyncio.create_task(self._run_loop(), name="snapshot-writer")
        logger.info("Snapshot writer started (every %.0fs)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Snapshot writer stopped")

    async def write_for_active_users(self) -> int:
        """Snapshot every user seen within the last hour. Returns the count.

        One user's failure is caught and logged rather than raised: an
        unpriceable position in one portfolio must not cost every other user
        their snapshot for this interval.
        """
        cutoff = iso_seconds_ago(3600)
        written = 0
        for user_id in await self._users.list_active_since(cutoff):
            try:
                await self._write_one(user_id)
                written += 1
            except Exception:
                logger.exception("Snapshot failed for %s", user_id)
        return written

    async def _write_one(self, user_id: str) -> None:
        service = build_trade_service(self._db, self._settings, self._price_cache, user_id)
        await service.write_snapshot()

    async def _run_loop(self) -> None:
        ticks = 0
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.write_for_active_users()
                ticks += 1
                # Pruning is cheap but pointless every 30s; hourly is plenty.
                if ticks % max(1, int(3600 / self._interval)) == 0:
                    removed = await self._prune_active_users()
                    if removed:
                        logger.info("Pruned %d expired snapshots", removed)
            except Exception:
                logger.exception("Snapshot write failed")

    async def _prune_active_users(self) -> int:
        """Prune every recently-active user's snapshot table.

        Scoped to the same "recently active" set `write_for_active_users`
        uses: an idle guest's snapshots are removed wholesale, along with
        the rest of the row, once `delete_expired_guests` reaps the profile.
        """
        cutoff = iso_seconds_ago(3600)
        removed = 0
        for user_id in await self._users.list_active_since(cutoff):
            try:
                service = build_trade_service(self._db, self._settings, self._price_cache, user_id)
                removed += await service.prune_snapshots(self._retention_days)
            except Exception:
                logger.exception("Pruning failed for %s", user_id)
        return removed
