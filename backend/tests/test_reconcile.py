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
        """Not watched and not held -- the reconciler must let it go."""
        await services.watchlist_repo.remove("AAPL")

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


class TestGlobalTracking:
    async def test_the_union_spans_every_user(self, seeded_db, settings, price_cache):
        """One user's watchlist must not be the whole tracked set."""
        from app.identity.store import UserStore
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        store = UserStore(seeded_db, settings)
        await store.mint_guest()
        second = await store.mint_guest()
        await seeded_db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            ("w1", second.id, "PYPL", "2026-01-01T00:00:00Z"),
        )

        source = StubDataSource(price_cache)
        reconciler = TickerReconciler(source, seeded_db, settings.market_capacity)
        tracked = await reconciler.compute_tracked_tickers()

        assert "PYPL" in tracked
        assert "AAPL" in tracked  # seeded for both

    async def test_a_ticker_another_user_holds_is_not_released(
        self, seeded_db, settings, price_cache
    ):
        """The correctness trap: releasing here evicts the cached price, and
        the other user's position then values at zero or fails outright."""
        from app.identity.store import UserStore
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        store = UserStore(seeded_db, settings)
        holder = await store.mint_guest()
        await seeded_db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p1", holder.id, "NVDA", 4.0, 100.0, "2026-01-01T00:00:00Z"),
        )
        source = StubDataSource(price_cache)
        await source.add_ticker("NVDA")
        reconciler = TickerReconciler(source, seeded_db, settings.market_capacity)

        await reconciler.release_if_unheld("NVDA")

        assert "NVDA" in source.get_tickers()

    async def test_a_ticker_nobody_watches_or_holds_is_released(
        self, seeded_db, settings, price_cache
    ):
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        source = StubDataSource(price_cache)
        await source.add_ticker("ZZZZ")
        reconciler = TickerReconciler(source, seeded_db, settings.market_capacity)

        await reconciler.release_if_unheld("ZZZZ")

        assert "ZZZZ" not in source.get_tickers()


class TestGlobalCapacity:
    async def test_ensure_tracked_refuses_past_the_global_cap(
        self, seeded_db, settings, price_cache
    ):
        """A global limit reported as WATCHLIST_FULL would tell a user their
        own watchlist is full when it holds three tickers."""
        import pytest

        from app.errors import MarketCapacityFullError
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        source = StubDataSource(price_cache)
        for index in range(3):
            await source.add_ticker(f"T{index}")
        reconciler = TickerReconciler(source, seeded_db, capacity=3)

        with pytest.raises(MarketCapacityFullError):
            await reconciler.ensure_tracked("NEWT")

    async def test_a_ticker_already_tracked_is_allowed_at_capacity(
        self, seeded_db, settings, price_cache
    ):
        """At the cap, re-watching something already tracked costs nothing."""
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        source = StubDataSource(price_cache)
        for index in range(3):
            await source.add_ticker(f"T{index}")
        reconciler = TickerReconciler(source, seeded_db, capacity=3)

        await reconciler.ensure_tracked("T1")  # must not raise
