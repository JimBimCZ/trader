"""The computed cache and data source that stand in for the ticking ones."""

from __future__ import annotations

import pytest

from app.market.deterministic import SESSION_SECONDS, seed_price
from app.market.deterministic_source import DeterministicDataSource, DeterministicPriceCache


@pytest.fixture
def cache() -> DeterministicPriceCache:
    return DeterministicPriceCache(tickers=["AAPL", "MSFT"])


class TestCache:
    def test_a_tracked_ticker_has_a_price(self, cache):
        update = cache.get("AAPL")
        assert update is not None
        assert update.price > 0

    def test_an_untracked_ticker_has_none(self, cache):
        """Trade validation depends on this: no price means a 409, not a fill at zero."""
        assert cache.get("NFLX") is None
        assert cache.get_price("NFLX") is None

    def test_lowercase_input_finds_the_ticker(self, cache):
        assert cache.get("aapl") is not None

    def test_get_all_covers_exactly_the_tracked_set(self, cache):
        assert sorted(cache.get_all()) == ["AAPL", "MSFT"]

    def test_the_session_baseline_is_the_seed_price(self, cache):
        assert cache.get("AAPL").session_open == seed_price("AAPL")

    def test_update_registers_a_ticker_rather_than_storing_a_price(self, cache):
        cache.update("NFLX", 999.0)
        assert "NFLX" in cache
        assert cache.get_price("NFLX") != 999.0

    def test_remove_stops_answering(self, cache):
        cache.remove("AAPL")
        assert "AAPL" not in cache
        assert cache.get("AAPL") is None

    def test_prices_are_stable_within_a_tick(self, cache):
        """The SSE generator emits on version change; a price moving between
        two reads of the same tick would make the stream disagree with itself."""
        tick = cache.current_tick()
        assert cache.build_update("AAPL", tick).price == cache.build_update("AAPL", tick).price

    def test_the_version_is_the_tick_index(self, cache):
        assert cache.version == cache.current_tick()
        assert (
            cache.build_update("AAPL", 100).timestamp != cache.build_update("AAPL", 101).timestamp
        )

    def test_consecutive_ticks_are_chained(self, cache):
        tick = cache.current_tick()
        assert (
            cache.build_update("AAPL", tick).previous_price
            == cache.build_update("AAPL", tick - 1).price
        )

    def test_a_session_opens_flat_rather_than_against_yesterday(self, cache):
        """Otherwise every row flashes full width once a day at UTC midnight."""
        first_tick = int(SESSION_SECONDS * 21_000 / 0.5)
        update = cache.build_update("AAPL", first_tick)
        assert update.previous_price == update.price
        assert update.direction == "flat"


class TestSource:
    async def test_start_tracks_the_given_tickers(self):
        cache = DeterministicPriceCache()
        source = DeterministicDataSource(cache)
        await source.start(["AAPL", "TSLA"])
        assert source.get_tickers() == ["AAPL", "TSLA"]

    async def test_add_and_remove(self, cache):
        source = DeterministicDataSource(cache)
        await source.add_ticker("nflx")
        assert "NFLX" in source.get_tickers()
        await source.remove_ticker("NFLX")
        assert "NFLX" not in source.get_tickers()

    async def test_stop_is_safe(self, cache):
        source = DeterministicDataSource(cache)
        await source.stop()
        await source.stop()


class TestBundleIndependence:
    """The serverless deployment installs neither numpy nor the Massive client.

    An import outside its branch — even one only reached to test a type — takes
    startup down there while passing every test on a machine that happens to
    have the package. These tests remove that asymmetry.
    """

    @staticmethod
    def _without(*blocked: str):
        """A meta-path hook that makes the named packages unimportable."""

        class Blocker:
            def find_module(self, name, path=None):
                return self.find_spec(name, path)

            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in blocked:
                    raise ImportError(f"No module named {name!r}")
                return None

        return Blocker()

    def test_the_deterministic_path_never_imports_the_simulator(self, monkeypatch):
        import sys

        from app.config import Settings
        from app.market.factory import create_market_data_source, create_price_cache

        for module in [m for m in sys.modules if m.startswith(("numpy", "app.market.simulator"))]:
            monkeypatch.delitem(sys.modules, module, raising=False)
        monkeypatch.setattr(sys, "meta_path", [self._without("numpy", "massive"), *sys.meta_path])

        settings = Settings(market_source="deterministic")
        source = create_market_data_source(create_price_cache(settings), settings)

        assert type(source).__name__ == "DeterministicDataSource"
        assert "numpy" not in sys.modules
