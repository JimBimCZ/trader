"""Tests for default seed data."""

from __future__ import annotations

from app.config import Settings
from app.db import DEFAULT_WATCHLIST, Database, seed_if_empty


class TestSeedIfEmpty:
    async def test_seeds_a_fresh_database(self, db: Database, settings: Settings):
        """A fresh database gets the default profile and watchlist."""
        assert await seed_if_empty(db, settings) is True

        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'default'")
        assert profile["cash_balance"] == 10_000.0

        rows = await db.fetch_all("SELECT ticker FROM watchlist ORDER BY added_at, ticker")
        assert {row["ticker"] for row in rows} == set(DEFAULT_WATCHLIST)

    async def test_does_not_reseed_an_existing_database(self, db: Database, settings: Settings):
        """Seeding twice leaves the data alone, including a changed balance."""
        await seed_if_empty(db, settings)
        await db.execute("UPDATE users_profile SET cash_balance = 42.0 WHERE id = 'default'")
        await db.commit()

        assert await seed_if_empty(db, settings) is False

        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'default'")
        assert profile["cash_balance"] == 42.0
        rows = await db.fetch_all("SELECT ticker FROM watchlist")
        assert len(rows) == len(DEFAULT_WATCHLIST)

    async def test_seeds_canonical_tickers(self, db: Database, settings: Settings):
        """Seeded tickers go through the same canonicalization as user input."""
        await seed_if_empty(db, settings)
        rows = await db.fetch_all("SELECT ticker FROM watchlist")
        assert all(row["ticker"] == row["ticker"].strip().upper() for row in rows)

    async def test_respects_configured_initial_cash(self, db: Database, tmp_path):
        """The starting balance comes from settings, not a hardcoded constant."""
        custom = Settings(db_path=tmp_path / "x.db", initial_cash=250.0)
        await seed_if_empty(db, custom)
        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'default'")
        assert profile["cash_balance"] == 250.0
