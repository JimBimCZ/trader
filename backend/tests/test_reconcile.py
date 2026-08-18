"""Tests for the tracked-ticker union rule."""

from __future__ import annotations


class TestComputeTrackedTickers:
    async def test_is_the_watchlist_when_nothing_is_held(self, services):
        tracked = await services.reconciler.compute_tracked_tickers()
        assert tracked == sorted(await services.watchlist_service.list())

    async def test_includes_held_tickers_that_are_not_watched(self, services):
        """The union covers positions the user no longer watches."""
        await services.track("PYPL", price=60.0)
        await services.trade_service.execute_trade("PYPL", "buy", 1)
        await services.watchlist_service.add("PYPL")
        await services.watchlist_service.remove("PYPL")

        assert "PYPL" in await services.reconciler.compute_tracked_tickers()

    async def test_excludes_a_closed_position(self, services):
        """Once fully sold and unwatched, a ticker leaves the union."""
        await services.track("PYPL", price=60.0)
        await services.trade_service.execute_trade("PYPL", "buy", 1)
        await services.trade_service.execute_trade("PYPL", "sell", 1)

        assert "PYPL" not in await services.reconciler.compute_tracked_tickers()


class TestEnsureTracked:
    async def test_adds_an_untracked_ticker(self, services):
        await services.reconciler.ensure_tracked("PYPL")
        assert "PYPL" in services.source.get_tickers()

    async def test_is_idempotent(self, services):
        await services.reconciler.ensure_tracked("PYPL")
        await services.reconciler.ensure_tracked("PYPL")
        assert services.source.get_tickers().count("PYPL") == 1


class TestReleaseIfUnheld:
    async def test_releases_a_ticker_with_no_position(self, services):
        await services.reconciler.release_if_unheld("AAPL")
        assert "AAPL" in services.source.removed

    async def test_refuses_to_release_a_held_ticker(self, services):
        """The single enforcement point for the held-ticker invariant."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 1)

        await services.reconciler.release_if_unheld("AAPL")

        assert "AAPL" not in services.source.removed
        assert "AAPL" in services.source.get_tickers()


class TestReconcile:
    async def test_adds_missing_and_drops_extra_tickers(self, services):
        """Reconcile forces the source to match the union exactly."""
        await services.source.add_ticker("BOGUS")
        await services.watchlist_service.add("PYPL")

        result = await services.reconciler.reconcile()

        assert "BOGUS" not in services.source.get_tickers()
        assert "PYPL" in services.source.get_tickers()
        assert result == sorted(set(result))

    async def test_keeps_held_tickers(self, services):
        await services.track("PYPL", price=60.0)
        await services.trade_service.execute_trade("PYPL", "buy", 1)
        await services.reconciler.reconcile()
        assert "PYPL" in services.source.get_tickers()
