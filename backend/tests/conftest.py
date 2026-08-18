"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

from app.config import Settings
from app.db import Database, init_db, open_connection, seed_if_empty
from app.market import PriceCache


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at a throwaway database, with the LLM mocked."""
    return Settings(db_path=tmp_path / "test.db", llm_mock=True, sim_seed=1234)


@pytest_asyncio.fixture
async def db(settings: Settings):
    """An initialized, unseeded database on a temp path."""
    conn = await open_connection(settings.db_path)
    database = Database(conn)
    await init_db(database)
    yield database
    await conn.close()


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
