"""Expiring idle guests.

A daily task in the container. On Vercel nothing runs between requests, so a
Cron entry posts to the admin route instead.
"""

from __future__ import annotations

import asyncio
import logging

from ..clock import iso_seconds_ago
from ..config import Settings
from ..identity import UserStore

logger = logging.getLogger(__name__)


class GuestCleaner:
    """Deletes guests idle past the TTL. The foreign keys cascade the rest."""

    def __init__(
        self, user_store: UserStore, settings: Settings, interval_seconds: float = 86400.0
    ) -> None:
        self._users = user_store
        self._settings = settings
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    async def run_once(self) -> int:
        cutoff = iso_seconds_ago(self._settings.guest_ttl_days * 86400)
        return await self._users.delete_expired_guests(cutoff)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop(), name="guest-cleanup")
        logger.info("Guest cleanup started (every %.0fs)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.run_once()
            except Exception:
                # Never let a cleanup failure take the process down.
                logger.exception("Guest cleanup failed")
