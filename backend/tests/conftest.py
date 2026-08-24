"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

from app.config import Settings
from app.db import Database, init_db, seed_if_empty
from app.db.postgres import PostgresDatabase, normalize_dsn
from app.market import PriceCache

TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://trader:trader@localhost:5432/trader")


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
    database = await PostgresDatabase.connect(settings.database_url, search_path=settings.db_schema)
    await init_db(database)
    yield database
    await database.close()
    admin = await asyncpg.connect(normalize_dsn(settings.database_url))
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{settings.db_schema}" CASCADE')
    finally:
        await admin.close()


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

    app = create_app(settings)
    with TestClient(app) as client:
        yield client
    # The app owns its pool and closes it in the lifespan; only the schema is
    # left behind, and the `db` fixture is not in play here to drop it.
    import asyncio

    async def _drop() -> None:
        admin = await asyncpg.connect(normalize_dsn(settings.database_url))
        try:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{settings.db_schema}" CASCADE')
        finally:
            await admin.close()

    asyncio.run(_drop())
