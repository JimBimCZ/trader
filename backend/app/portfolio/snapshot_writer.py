"""Background task recording portfolio value over time."""

from __future__ import annotations

import asyncio
import logging

from .service import TradeService

logger = logging.getLogger(__name__)


class SnapshotWriter:
    """Writes a portfolio snapshot on an interval and prunes old rows.

    Trades write their own snapshot immediately, so the P&L chart reacts at
    once; this task covers the periods between trades.
    """

    def __init__(
        self,
        trade_service: TradeService,
        interval: float = 30.0,
        retention_days: int = 7,
    ) -> None:
        self._service = trade_service
        self._interval = interval
        self._retention_days = retention_days
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Write an immediate snapshot, then start the periodic task.

        The immediate write means the P&L chart has a point at t=0 instead of
        being empty for the first interval.
        """
        await self._service.write_snapshot()
        self._task = asyncio.create_task(self._run_loop(), name="snapshot-writer")
        logger.info("Snapshot writer started (every %.0fs)", self._interval)

    async def stop(self) -> None:
        """Stop the task. Safe to call more than once."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Snapshot writer stopped")

    async def _run_loop(self) -> None:
        ticks = 0
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._service.write_snapshot()
                ticks += 1
                # Pruning is cheap but pointless every 30s; hourly is plenty.
                if ticks % max(1, int(3600 / self._interval)) == 0:
                    removed = await self._service.prune_snapshots(self._retention_days)
                    if removed:
                        logger.info("Pruned %d expired snapshots", removed)
            except Exception:
                logger.exception("Snapshot write failed")
