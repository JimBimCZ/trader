"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import pytest
import pytest_asyncio

from app.config import Settings
from app.db import Database, init_db, seed_if_empty
from app.db.postgres import PostgresDatabase, normalize_dsn
from app.market import PriceCache

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://trader:trader@localhost:5432/trader")

#: The exact shape `db_schema` below hands out. Both the session-scoped sweep and
#: `_provisioned_schema`'s callers rely on this to recognize their own throwaway
#: schemas and nothing else -- it must never be loose enough to match "public"
#: or an application schema.
_TEST_SCHEMA_RE = re.compile(r"^test_[0-9a-f]{12}$")


async def _drop_schema(dsn: str, schema: str) -> None:
    """Drop one throwaway schema, tolerating one that was never created."""
    admin = await asyncpg.connect(normalize_dsn(dsn))
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await admin.close()


@asynccontextmanager
async def _provisioned_schema(dsn: str, schema: str) -> AsyncIterator[PostgresDatabase]:
    """Connect to a throwaway schema and guarantee it is dropped.

    Factored out of the `db` fixture (and mirrored by `api_client`, which owns
    its schema through the app's lifespan instead of a `PostgresDatabase` it
    holds directly) so the try/finally can be exercised by a plain test rather
    than by forcing pytest's fixture machinery to fail. Before this, the drop
    only ran on the path that reached the fixture's `yield`; a failure in
    `init_db` -- called by the caller, inside this `async with` block -- left
    the schema behind forever. See tests/db/test_schema_cleanup.py.
    """
    database = await PostgresDatabase.connect(dsn, search_path=schema)
    try:
        yield database
    finally:
        await database.close()
        await _drop_schema(dsn, schema)


async def sweep_orphaned_test_schemas(dsn: str) -> list[str]:
    """Drop every `test_*` schema matching the fixture-generated pattern.

    Guarded twice: the SQL only selects names starting with `test_`, and the
    Python-side regex re-checks the full `test_<12 hex chars>` shape before
    any DROP runs. Neither pass can match "public" or an application schema,
    so a bug in one layer does not make the other layer dangerous.

    Returns the names actually dropped, so callers (and tests) can assert on
    what happened rather than just on "it didn't crash".
    """
    admin = await asyncpg.connect(normalize_dsn(dsn))
    try:
        rows = await admin.fetch(
            r"SELECT schema_name FROM information_schema.schemata "
            r"WHERE schema_name LIKE 'test\_%' ESCAPE '\'"
        )
        dropped: list[str] = []
        for row in rows:
            name = row["schema_name"]
            if _TEST_SCHEMA_RE.match(name):
                await admin.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
                dropped.append(name)
        return dropped
    finally:
        await admin.close()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_orphaned_test_schemas() -> None:
    """Drop any `test_*` schemas left behind by a previously crashed run.

    Runs once, before any test, so a crashed run is self-healing rather than
    something that poisons every run after it -- see the 26 orphaned schemas
    that once flaked test_search_path.py.
    """
    asyncio.run(sweep_orphaned_test_schemas(TEST_DSN))


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def db_schema() -> str:
    """A unique schema name per test, so tests never share tables."""
    return f"test_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def settings(db_schema: str) -> Settings:
    """Settings pointed at a throwaway schema, with the LLM mocked."""
    return Settings(
        database_url=TEST_DSN,
        db_schema=db_schema,
        llm_mock=True,
        sim_seed=1234,
    )


@pytest_asyncio.fixture
async def db(settings: Settings):
    """An initialized, unseeded database isolated in its own schema."""
    async with _provisioned_schema(settings.database_url, settings.db_schema) as database:
        await init_db(database)
        yield database


@pytest_asyncio.fixture
async def seeded_db(db: Database, settings: Settings):
    """An initialized database with the default profile and watchlist."""
    await seed_if_empty(db, settings)
    return db


@pytest.fixture
def price_cache() -> PriceCache:
    """A bare price cache with no background task; tests call update() directly."""
    return PriceCache()


@pytest.fixture
def priced_cache(price_cache: PriceCache) -> PriceCache:
    """A price cache pre-populated with the default watchlist at seed prices."""
    from app.market.seed_prices import SEED_PRICES

    for ticker, price in SEED_PRICES.items():
        price_cache.update(ticker, price, session_open=price)
    return price_cache


@pytest_asyncio.fixture
async def services(seeded_db, settings: Settings, price_cache: PriceCache):
    """Fully wired services against a seeded temp database and a stub source."""
    from tests.conftest_services import Services

    built = Services(seeded_db, settings, price_cache)
    await built.reconciler.reconcile()
    return built


@pytest.fixture
def api_client(settings: Settings):
    """A TestClient over a fully started app in its own schema.

    Entering the context manager runs the real lifespan, so the simulator,
    history collector, and snapshot writer are all live.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    try:
        app = create_app(settings)
        with TestClient(app) as client:
            yield client
    finally:
        # The app owns its pool and closes it in the lifespan; only the schema is
        # left behind, and the `db` fixture is not in play here to drop it.
        asyncio.run(_drop_schema(settings.database_url, settings.db_schema))
