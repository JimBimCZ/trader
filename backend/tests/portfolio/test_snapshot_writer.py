"""Tests for the periodic portfolio snapshot task."""

from __future__ import annotations

import asyncio

from app.identity.store import UserStore
from app.portfolio.service import TradeService
from app.portfolio.snapshot_writer import SnapshotWriter


def _writer(services, **kwargs) -> SnapshotWriter:
    """A SnapshotWriter wired against the `services` fixture's temp database.

    `services.trade_service` is scoped to the default user, which is seeded
    with a fresh `last_seen_at`, so it falls inside `write_for_active_users`'
    one-hour window and these tests can keep asserting through it.
    """
    store = UserStore(services.db, services.settings)
    return SnapshotWriter(services.db, services.settings, store, services.price_cache, **kwargs)


class TestSnapshotWriter:
    async def test_writes_immediately_on_start(self, services):
        """The first interval must not be dead time on a long interval."""
        before = len(await services.trade_service.get_history())
        writer = _writer(services, interval=60)
        await writer.start()
        try:
            assert len(await services.trade_service.get_history()) == before + 1
        finally:
            await writer.stop()

    async def test_writes_again_on_each_interval(self, services):
        # Postgres round-trips over the loopback socket where SQLite wrote
        # in-process, so the window needs more margin above `interval` than
        # it did against the file-backed database.
        writer = _writer(services, interval=0.02)
        await writer.start()
        try:
            await asyncio.sleep(0.09)
        finally:
            await writer.stop()
        assert len(await services.trade_service.get_history()) >= 3

    async def test_stop_is_idempotent(self, services):
        writer = _writer(services, interval=0.01)
        await writer.start()
        await writer.stop()
        await writer.stop()

    async def test_a_failing_write_does_not_kill_the_loop(self, services, monkeypatch):
        """One unvaluable moment must not stop snapshots forever.

        The writer builds its own per-user `TradeService` on every tick (see
        `build_trade_service`), so there is no single service instance to
        monkeypatch any more -- the flaky behaviour is installed on the class.
        """
        writer = _writer(services, interval=0.02)
        calls = {"n": 0}
        real = TradeService.write_snapshot

        async def flaky(self):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("transient")
            return await real(self)

        monkeypatch.setattr(TradeService, "write_snapshot", flaky)
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
        # The seeded t=0 point would be pruned along with the old one and
        # muddy the count, so this starts from an empty history.
        await services.snapshots.delete_all()
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
        await services.snapshots.delete_all()
        await services.snapshots.insert(10_000.0)
        await services.db.commit()
        assert await services.trade_service.prune_snapshots(retention_days=7) == 0


class TestCoversActiveUsers:
    async def test_a_snapshot_is_written_for_every_recently_seen_user(
        self, seeded_db, settings, priced_cache
    ):
        from app.identity.store import UserStore
        from app.portfolio.snapshot_writer import SnapshotWriter

        store = UserStore(seeded_db, settings)
        first = await store.mint_guest()
        second = await store.mint_guest()
        writer = SnapshotWriter(seeded_db, settings, store, priced_cache)

        await writer.write_for_active_users()

        for user in (first, second):
            rows = await seeded_db.fetch_all(
                "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?",
                (user.id,),
            )
            # The seeded t=0 point, plus the one this pass wrote.
            assert len(rows) == 2

    async def test_an_idle_user_gets_no_snapshot(self, seeded_db, settings, priced_cache):
        """Writing for every user forever turns a dormant demo into a growing
        write load with nobody reading the result."""
        from app.identity.store import UserStore
        from app.portfolio.snapshot_writer import SnapshotWriter

        store = UserStore(seeded_db, settings)
        idle = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", idle.id),
        )
        # Minting seeded a t=0 point; deleting it means anything found below
        # was written by this pass rather than left over from the seed.
        await seeded_db.execute("DELETE FROM portfolio_snapshots WHERE user_id = ?", (idle.id,))
        writer = SnapshotWriter(seeded_db, settings, store, priced_cache)

        await writer.write_for_active_users()

        rows = await seeded_db.fetch_all(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?", (idle.id,)
        )
        assert rows == []

    async def test_one_user_failing_does_not_stop_the_others(
        self, seeded_db, settings, priced_cache
    ):
        """A single unpriceable position must not cost every other user their
        snapshot for that interval."""
        from app.identity.store import UserStore
        from app.portfolio.snapshot_writer import SnapshotWriter

        store = UserStore(seeded_db, settings)
        broken = await store.mint_guest()
        healthy = await store.mint_guest()
        await seeded_db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p-broken", broken.id, "NOPRICE", 1.0, 10.0, "2026-01-01T00:00:00Z"),
        )
        writer = SnapshotWriter(seeded_db, settings, store, priced_cache)

        await writer.write_for_active_users()

        rows = await seeded_db.fetch_all(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?",
            (healthy.id,),
        )
        # The seeded t=0 point, plus the one written despite the other user
        # raising mid-pass.
        assert len(rows) == 2


class TestTheLifespanSkipsTheWriterOnServerless:
    """The market source, the history collector and the guest cleaner all check
    `settings.serverless`; the writer did not.

    Its `start()` is not free any more: it awaits one snapshot write per user
    active in the last hour before the lifespan yields, so every Vercel cold
    start would pay N Neon round trips before serving a single request, on the
    target with the tightest time budget -- and the loop it creates is never
    scheduled between requests anyway. `GET /api/portfolio` calls
    `write_snapshot_if_stale()` there instead.
    """

    @staticmethod
    def _started_writers(settings, monkeypatch) -> list:
        from fastapi.testclient import TestClient

        import app.main as main_module
        from tests.conftest import CLIENT_BASE_URL, _drop_schema

        started: list = []

        async def recording_start(self) -> None:
            started.append(self)

        monkeypatch.setattr(main_module.SnapshotWriter, "start", recording_start)
        try:
            with TestClient(main_module.create_app(settings), base_url=CLIENT_BASE_URL):
                pass
        finally:
            asyncio.run(_drop_schema(settings.database_url, settings.db_schema))
        return started

    def test_no_writer_starts_when_the_platform_freezes_the_process(self, settings, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")

        assert self._started_writers(settings, monkeypatch) == []

    def test_the_writer_still_starts_on_a_long_lived_process(self, settings, monkeypatch):
        """The guard must not have turned the background task off everywhere."""
        monkeypatch.delenv("VERCEL", raising=False)

        assert len(self._started_writers(settings, monkeypatch)) == 1
