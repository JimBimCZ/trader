"""Tests for the periodic portfolio snapshot task."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.portfolio.snapshot_writer import SnapshotWriter


class TestSnapshotWriter:
    async def test_writes_immediately_on_start(self, services):
        """A point at t=0 means the P&L chart is never empty on first load."""
        writer = SnapshotWriter(services.trade_service, interval=60)
        await writer.start()
        try:
            assert len(await services.trade_service.get_history()) == 1
        finally:
            await writer.stop()

    async def test_writes_again_on_each_interval(self, services):
        writer = SnapshotWriter(services.trade_service, interval=0.02)
        await writer.start()
        try:
            await asyncio.sleep(0.07)
        finally:
            await writer.stop()
        assert len(await services.trade_service.get_history()) >= 3

    async def test_stop_is_idempotent(self, services):
        writer = SnapshotWriter(services.trade_service, interval=0.01)
        await writer.start()
        await writer.stop()
        await writer.stop()

    async def test_a_failing_write_does_not_kill_the_loop(self, services):
        """One unvaluable moment must not stop snapshots forever."""
        writer = SnapshotWriter(services.trade_service, interval=0.02)
        calls = {"n": 0}
        real = services.trade_service.write_snapshot

        async def flaky():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("transient")
            return await real()

        services.trade_service.write_snapshot = AsyncMock(side_effect=flaky)
        await writer.start()
        try:
            await asyncio.sleep(0.09)
        finally:
            await writer.stop()

        assert calls["n"] >= 3

    async def test_an_unvaluable_portfolio_skips_rather_than_raises(self, services):
        """A held ticker with no price yields no snapshot, not a crash."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 1)
        services.price_cache.remove("AAPL")

        assert await services.trade_service.write_snapshot() is None


class TestPruning:
    async def test_prunes_snapshots_older_than_the_window(self, services):
        """Retention bounds a table that otherwise grows forever."""
        await services.snapshots.insert(10_000.0)
        await services.db.commit()
        await services.db.execute(
            "UPDATE portfolio_snapshots SET recorded_at = '2020-01-01T00:00:00Z'"
        )
        await services.db.commit()
        await services.snapshots.insert(10_500.0)
        await services.db.commit()

        removed = await services.trade_service.prune_snapshots(retention_days=7)

        assert removed == 1
        remaining = await services.trade_service.get_history()
        assert [s.total_value for s in remaining] == [10_500.0]

    async def test_keeps_recent_snapshots(self, services):
        await services.snapshots.insert(10_000.0)
        await services.db.commit()
        assert await services.trade_service.prune_snapshots(retention_days=7) == 0
