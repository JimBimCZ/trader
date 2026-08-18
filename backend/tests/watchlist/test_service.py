"""Tests for watchlist mutations and the tracked-ticker invariants."""

from __future__ import annotations

import pytest

from app.errors import InvalidTickerError, TickerNotFoundError, WatchlistFullError

#: Fifteen valid letter-only symbols, enough to reach the 25-ticker cap on
#: top of the ten seeded defaults.
FILLERS = [f"Z{chr(65 + i)}" for i in range(15)]


class TestList:
    async def test_returns_the_seeded_watchlist(self, services):
        """A fresh install watches the ten default tickers."""
        assert len(await services.watchlist_service.list()) == 10

    async def test_preserves_insertion_order(self, services):
        """Order is by added_at, so the UI can render rows stably."""
        before = await services.watchlist_service.list()
        after = await services.watchlist_service.add("PYPL")
        assert after == [*before, "PYPL"]


class TestAdd:
    async def test_adds_a_new_ticker(self, services):
        assert "PYPL" in await services.watchlist_service.add("PYPL")

    async def test_canonicalizes_input(self, services):
        """Lowercase input cannot create a duplicate instrument."""
        result = await services.watchlist_service.add("  pypl ")
        assert "PYPL" in result
        assert "pypl" not in result

    async def test_is_idempotent(self, services):
        """Adding an existing ticker changes nothing and does not error."""
        first = await services.watchlist_service.add("PYPL")
        second = await services.watchlist_service.add("PYPL")
        assert first == second

    async def test_starts_tracking_the_new_ticker(self, services):
        await services.watchlist_service.add("PYPL")
        assert "PYPL" in services.source.get_tickers()

    async def test_rejects_an_invalid_ticker(self, services):
        with pytest.raises(InvalidTickerError):
            await services.watchlist_service.add("BRK.B")

    async def test_enforces_the_cap(self, services):
        """The cap bounds both the SSE payload and Massive's rate budget."""
        for ticker in FILLERS:
            await services.watchlist_service.add(ticker)
        with pytest.raises(WatchlistFullError):
            await services.watchlist_service.add("ZZZZZ")

    async def test_a_duplicate_does_not_count_against_the_cap(self, services):
        """Re-adding an existing ticker at the cap is still allowed."""
        for ticker in FILLERS:
            await services.watchlist_service.add(ticker)
        assert len(await services.watchlist_service.add("AAPL")) == 25


class TestRemove:
    async def test_removes_the_ticker(self, services):
        result = await services.watchlist_service.remove("AAPL")
        assert "AAPL" not in result

    async def test_stops_tracking_an_unheld_ticker(self, services):
        """With no position open, the price feed can safely stop."""
        await services.watchlist_service.remove("AAPL")
        assert "AAPL" not in services.source.get_tickers()

    async def test_keeps_tracking_a_ticker_that_is_still_held(self, services):
        """Removing a held ticker must not stop its price feed.

        remove_ticker also evicts the cached price, so doing it here would
        make the position unvaluable and break the heatmap and P&L chart.
        """
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 5)

        await services.watchlist_service.remove("AAPL")

        assert "AAPL" not in await services.watchlist_service.list()
        assert "AAPL" in services.source.get_tickers()
        assert services.price_cache.get_price("AAPL") == 190.0

    async def test_a_held_but_unwatched_position_still_values(self, services):
        """The portfolio remains reportable after un-watching a holding."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 5)
        await services.watchlist_service.remove("AAPL")

        view = await services.trade_service.get_portfolio()
        assert view.positions[0].ticker == "AAPL"
        assert view.positions[0].current_price == 190.0

    async def test_removing_an_absent_ticker_is_a_404(self, services):
        with pytest.raises(TickerNotFoundError):
            await services.watchlist_service.remove("PYPL")

    async def test_rejects_an_invalid_ticker(self, services):
        with pytest.raises(InvalidTickerError):
            await services.watchlist_service.remove("BRK.B")
