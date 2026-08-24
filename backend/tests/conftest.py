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

#: The exact shape `db_schema` below hands out. The session-scoped sweep relies
#: on this to recognize its own throwaway schemas and nothing else -- it must
#: never be loose enough to match "public" or an application schema.
_TEST_SCHEMA_RE = re.compile(r"^test_[0-9a-f]{12}$")

#: Every disposable schema name this suite generates: `db_schema` below
#: (`test_<12 hex>`) and `test_search_path.py`'s hand-rolled probes
#: (`probe_<8 hex>`). `_drop_schema` refuses anything outside this shape, so
#: "public" or an application schema can never reach a DROP statement through
#: it -- present caller or future one.
_DROPPABLE_SCHEMA_RE = re.compile(r"^(test|probe)_[0-9a-f]{6,32}$")


async def _drop_schema(dsn: str, schema: str) -> None:
    """Drop one throwaway schema, tolerating one that was never created.

    Refuses, loudly, anything that doesn't match a disposable test/probe
    schema name -- this is the single chokepoint every fixture and helper in
    this file drops a schema through, so a mistake here is the one thing that
    could turn a test run into `DROP SCHEMA public CASCADE` against whatever
    database `TEST_DATABASE_URL` happens to point at.
    """
    if not _DROPPABLE_SCHEMA_RE.match(schema):
        raise ValueError(
            f"refusing to drop schema {schema!r}: it does not match a disposable "
            f"test/probe schema name, so this is almost certainly a mistake"
        )
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

    Guarded three times over: the SQL only selects names starting with
    `test_`; the Python-side `_TEST_SCHEMA_RE` re-checks the full
    `test_<12 hex chars>` shape before a name is even considered a match; and
    the actual DROP runs through `_drop_schema`, which re-validates against
    its own (slightly looser, to also cover `probe_*`) pattern. No single
    layer failing can turn this into a `DROP SCHEMA public`.

    Returns the names actually dropped, so callers (and tests) can assert on
    what happened rather than just on "it didn't crash".

    Scoping hazard: this sweeps every `test_*` schema in the target database,
    not just ones this session created. It runs autouse and session-scoped
    (see `_cleanup_orphaned_test_schemas` below), and two tests in
    tests/db/test_schema_cleanup.py also call it directly mid-run. Fine under
    one pytest session at a time -- which is the only way this suite runs
    today -- but two concurrent sessions against the same database (two
    terminals, or pytest-xdist if it is ever added) would each drop the
    other's live schemas out from under it. Not fixed here; flagged so it
    isn't rediscovered as a mystery "relation does not exist" failure.
    """
    admin = await asyncpg.connect(normalize_dsn(dsn))
    try:
        rows = await admin.fetch(
            r"SELECT schema_name FROM information_schema.schemata "
            r"WHERE schema_name LIKE 'test\_%' ESCAPE '\'"
        )
        matches = [row["schema_name"] for row in rows if _TEST_SCHEMA_RE.match(row["schema_name"])]
    finally:
        await admin.close()

    # Dropped through _drop_schema, not inline, so each name is re-checked
    # against its guard before the DROP runs -- not "the same chokepoint every
    # schema in this suite goes through": test_schema_cleanup.py's lookalike
    # names (test_short, test_GGGGGGGGGGGG, ...) are deliberately shaped to
    # fail _DROPPABLE_SCHEMA_RE and so cannot route through here either.
    for name in matches:
        await _drop_schema(dsn, name)
    return matches


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
