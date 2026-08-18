"""Tests for the background history collector."""

from __future__ import annotations

import asyncio

from app.history import HistoryCollector, HistoryStore
from app.market import PriceCache


class TestCollector:
    async def test_seeds_from_the_existing_cache_on_start(self):
        """Prices already cached are captured without waiting for a tick."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        store = HistoryStore()

        collector = HistoryCollector(cache, store, interval=0.01)
        await collector.start()
        try:
            assert store.get("AAPL") == [(cache.get("AAPL").timestamp, 190.0)]
        finally:
            await collector.stop()

    async def test_collects_subsequent_updates(self):
        cache = PriceCache()
        store = HistoryStore()
        collector = HistoryCollector(cache, store, interval=0.01)
        await collector.start()
        try:
            cache.update("AAPL", 190.0, timestamp=1.0)
            await asyncio.sleep(0.05)
            cache.update("AAPL", 191.0, timestamp=2.0)
            await asyncio.sleep(0.05)
        finally:
            await collector.stop()

        assert store.get("AAPL") == [(1.0, 190.0), (2.0, 191.0)]

    async def test_stop_is_idempotent(self):
        """Calling stop twice is safe, matching the market source contract."""
        collector = HistoryCollector(PriceCache(), HistoryStore(), interval=0.01)
        await collector.start()
        await collector.stop()
        await collector.stop()

    async def test_a_failing_poll_does_not_kill_the_loop(self, monkeypatch):
        """One bad read must not stop history collection for good."""
        cache = PriceCache()
        store = HistoryStore()
        collector = HistoryCollector(cache, store, interval=0.01)

        calls = {"n": 0}
        original = cache.get_all

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient")
            return original()

        await collector.start()
        monkeypatch.setattr(cache, "get_all", flaky)
        try:
            cache.update("AAPL", 190.0, timestamp=1.0)
            await asyncio.sleep(0.08)
        finally:
            await collector.stop()

        assert store.get("AAPL") == [(1.0, 190.0)]
