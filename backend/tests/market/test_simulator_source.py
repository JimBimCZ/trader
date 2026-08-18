"""Integration tests for SimulatorDataSource."""

import asyncio

import pytest

from app.market.cache import PriceCache
from app.market.simulator import GBMSimulator, SimulatorDataSource


@pytest.mark.asyncio
class TestSimulatorDataSource:
    """Integration tests for the SimulatorDataSource."""

    async def test_start_populates_cache(self):
        """Test that start() immediately populates the cache."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "GOOGL"])

        # Cache should have seed prices immediately (before first loop tick)
        assert cache.get("AAPL") is not None
        assert cache.get("GOOGL") is not None

        await source.stop()

    async def test_prices_update_over_time(self):
        """Test that prices are updated periodically."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.05)
        await source.start(["AAPL"])

        initial_version = cache.version
        await asyncio.sleep(0.3)  # Several update cycles

        # Version should have incremented (prices updated)
        assert cache.version > initial_version

        await source.stop()

    async def test_stop_is_clean(self):
        """Test that stop() is clean and idempotent."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL"])
        await source.stop()
        # Double stop should not raise
        await source.stop()

    async def test_add_ticker(self):
        """Test adding a ticker dynamically."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL"])

        await source.add_ticker("TSLA")
        assert "TSLA" in source.get_tickers()
        assert cache.get("TSLA") is not None

        await source.stop()

    async def test_remove_ticker(self):
        """Test removing a ticker."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "TSLA"])

        await source.remove_ticker("TSLA")
        assert "TSLA" not in source.get_tickers()
        assert cache.get("TSLA") is None

        await source.stop()

    async def test_get_tickers(self):
        """Test getting the list of active tickers."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "GOOGL"])

        tickers = source.get_tickers()
        assert set(tickers) == {"AAPL", "GOOGL"}

        await source.stop()

    async def test_empty_start(self):
        """Test starting with no tickers."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start([])

        assert len(cache) == 0
        assert source.get_tickers() == []

        await source.stop()

    async def test_exception_resilience(self):
        """Test that simulator continues running after errors."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.05)

        # Start with a valid ticker
        await source.start(["AAPL"])

        # Wait for some updates
        await asyncio.sleep(0.15)

        # Task should still be running
        assert source._task is not None
        assert not source._task.done()

        await source.stop()

    async def test_custom_update_interval(self):
        """Test using a custom update interval."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.01)
        await source.start(["AAPL"])

        initial_version = cache.version
        await asyncio.sleep(0.05)  # Should get ~5 updates

        # Should have multiple updates with fast interval
        assert cache.version > initial_version + 2

        await source.stop()

    async def test_custom_event_probability(self):
        """Test creating source with custom event probability."""
        cache = PriceCache()
        # Very high event probability for testing
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1, event_probability=1.0)
        await source.start(["AAPL"])

        # Just verify it starts and stops cleanly
        await asyncio.sleep(0.2)
        await source.stop()


class TestSimulatorRegressions:
    """Regressions for the three bugs found in the shipped market module."""

    @pytest.mark.asyncio
    async def test_dt_is_derived_from_update_interval(self):
        """dt must track the real tick rate, or volatility is silently rescaled.

        The simulator used to construct GBMSimulator without passing dt, so it
        always fell back to a hardcoded 500ms constant. Setting update_interval
        to 100ms then produced 5x the configured volatility.
        """
        cache = PriceCache()
        source = SimulatorDataSource(cache, update_interval=0.1)
        await source.start(["AAPL"])
        try:
            expected = 0.1 / GBMSimulator.TRADING_SECONDS_PER_YEAR
            assert source._sim._dt == pytest.approx(expected)
        finally:
            await source.stop()

    @pytest.mark.asyncio
    async def test_default_interval_keeps_the_original_dt(self):
        """The default 500ms interval still yields the original DEFAULT_DT."""
        cache = PriceCache()
        source = SimulatorDataSource(cache, update_interval=0.5)
        await source.start(["AAPL"])
        try:
            assert source._sim._dt == pytest.approx(GBMSimulator.DEFAULT_DT)
        finally:
            await source.stop()

    @pytest.mark.asyncio
    async def test_lowercase_ticker_does_not_create_a_second_instrument(self):
        """add_ticker('aapl') must not create a duplicate alongside AAPL.

        The simulator source did not canonicalize, so a lowercase ticker became
        an independent instrument with its own random seed price, and both
        streamed to the UI at once.
        """
        cache = PriceCache()
        source = SimulatorDataSource(cache)
        await source.start(["AAPL"])
        try:
            await source.add_ticker("aapl")
            assert source.get_tickers() == ["AAPL"]
            assert len(cache) == 1
        finally:
            await source.stop()

    @pytest.mark.asyncio
    async def test_start_canonicalizes_its_ticker_list(self):
        """Tickers passed to start() are canonicalized too, not just add_ticker's."""
        cache = PriceCache()
        source = SimulatorDataSource(cache)
        await source.start([" msft ", "nvda"])
        try:
            assert sorted(source.get_tickers()) == ["MSFT", "NVDA"]
        finally:
            await source.stop()

    @pytest.mark.asyncio
    async def test_remove_ticker_canonicalizes(self):
        """A lowercase removal still removes the canonical instrument."""
        cache = PriceCache()
        source = SimulatorDataSource(cache)
        await source.start(["AAPL", "MSFT"])
        try:
            await source.remove_ticker("aapl")
            assert source.get_tickers() == ["MSFT"]
            assert "AAPL" not in cache
        finally:
            await source.stop()

    @pytest.mark.asyncio
    async def test_seeded_runs_are_reproducible(self):
        """The same SIM_SEED produces the same price path."""
        results = []
        for _ in range(2):
            cache = PriceCache()
            source = SimulatorDataSource(cache, update_interval=0.01, seed=1234)
            await source.start(["AAPL", "MSFT"])
            await asyncio.sleep(0.05)
            await source.stop()
            results.append({t: u.price for t, u in cache.get_all().items()})
        assert results[0] == results[1]

    @pytest.mark.asyncio
    async def test_start_records_the_seed_price_as_session_open(self):
        """The seed price becomes the session baseline for daily change %."""
        cache = PriceCache()
        source = SimulatorDataSource(cache, seed=7)
        await source.start(["AAPL"])
        try:
            update = cache.get("AAPL")
            assert update is not None
            assert update.session_open == update.price
            assert update.daily_change_percent == 0.0
        finally:
            await source.stop()
