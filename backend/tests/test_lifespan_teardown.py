"""A failed startup must unwind whatever it already started.

The pool used to be closed by an `except` around the migration block only,
and everything after it -- computing tracked tickers, starting the market
source, the history collector, the snapshot writer -- ran unprotected. The
`try/finally` that closes the pool does not begin until the `yield`, so a
raise partway through startup leaked the pool AND left the market source
running. An AsyncExitStack now registers each subsystem's teardown at the
moment it starts, so the unwind is automatic and in reverse order.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import create_app
from tests.conftest import _drop_schema


@pytest.fixture(autouse=True)
def _drop_the_schema_these_tests_create(settings):
    """These build the app directly rather than through `api_client`, so no
    other fixture owns the throwaway schema the lifespan creates."""
    yield
    import asyncio

    asyncio.run(_drop_schema(settings.database_url, settings.db_schema))


@pytest.fixture
def captured_db(monkeypatch):
    """Hold on to the database the lifespan opens, so we can inspect it."""
    opened = []
    real_open = main_module.open_database

    async def capturing_open(settings):
        db = await real_open(settings)
        opened.append(db)
        return db

    monkeypatch.setattr(main_module, "open_database", capturing_open)
    return opened


@pytest.fixture
def stopped_sources(monkeypatch):
    """Record stop() on whatever market source the lifespan builds."""
    stopped = []
    real_create = main_module.create_market_data_source

    def creating(price_cache, settings):
        source = real_create(price_cache, settings)
        real_stop = source.stop

        async def recording_stop():
            stopped.append(source)
            return await real_stop()

        source.stop = recording_stop
        return source

    monkeypatch.setattr(main_module, "create_market_data_source", creating)
    return stopped


class TestStartupFailureUnwinds:
    def test_a_failure_after_the_source_starts_still_closes_the_pool(
        self, settings, monkeypatch, captured_db, stopped_sources
    ):
        """The gap the old `except` left open: this failure point is past the
        migration block, so nothing used to close the pool."""

        async def boom(self):
            raise RuntimeError("simulated late startup failure")

        monkeypatch.setattr(main_module.SnapshotWriter, "start", boom)

        with pytest.raises(RuntimeError, match="simulated late startup failure"):
            with TestClient(create_app(settings)):
                pass

        assert captured_db, "the lifespan never opened a database"
        assert captured_db[0]._pool.is_closing(), "the connection pool leaked"

    def test_a_failure_after_the_source_starts_also_stops_the_source(
        self, settings, monkeypatch, captured_db, stopped_sources
    ):
        """The half that widening the try/except would not have fixed: the
        market source is already running by this point."""

        async def boom(self):
            raise RuntimeError("simulated late startup failure")

        monkeypatch.setattr(main_module.SnapshotWriter, "start", boom)

        with pytest.raises(RuntimeError, match="simulated late startup failure"):
            with TestClient(create_app(settings)):
                pass

        assert stopped_sources, "the market source was left running"

    def test_a_clean_startup_still_tears_down_in_order(self, settings, captured_db):
        """Guards against a fix that unwinds on failure but breaks the normal
        shutdown path."""
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/health").status_code == 200

        assert captured_db[0]._pool.is_closing()
