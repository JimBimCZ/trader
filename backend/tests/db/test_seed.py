"""Tests for default seed data."""

from __future__ import annotations

from app.config import Settings
from app.db import DEFAULT_WATCHLIST, Database, seed_user
from tests.conftest import create_seeded_user


class TestSeedUser:
    async def test_seeds_a_fresh_user(self, db: Database, settings: Settings):
        """A newly created user gets their starting cash and watchlist."""
        await create_seeded_user(db, settings, "alice")

        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'alice'")
        assert profile["cash_balance"] == 10_000.0

        rows = await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = 'alice'")
        assert {row["ticker"] for row in rows} == set(DEFAULT_WATCHLIST)

    async def test_seeds_every_user_not_just_the_first(self, db: Database, settings: Settings):
        """The single-user form asked "is the database empty?", which is false
        the moment one user exists -- so it would have seeded nobody after."""
        await create_seeded_user(db, settings, "alice")
        await create_seeded_user(db, settings, "bob")

        for user_id in ("alice", "bob"):
            rows = await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = ?", (user_id,))
            assert len(rows) == len(DEFAULT_WATCHLIST)

    async def test_reseeding_leaves_an_edited_watchlist_alone(
        self, db: Database, settings: Settings
    ):
        """Seeding is idempotent: it restores what is missing, duplicates nothing."""
        await create_seeded_user(db, settings, "alice")
        await db.execute("DELETE FROM watchlist WHERE user_id = 'alice' AND ticker = 'AAPL'")

        await seed_user(db, settings, "alice")

        rows = await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = 'alice'")
        assert len(rows) == len(DEFAULT_WATCHLIST)
        assert len({row["ticker"] for row in rows}) == len(DEFAULT_WATCHLIST)

        # The t=0 snapshot is guarded too. Unguarded, a repair pass would put
        # a second `initial_cash` point, dated today, into a chart that has
        # long since moved off that value.
        snapshots = await db.fetch_all(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = 'alice'"
        )
        assert len(snapshots) == 1

    async def test_seeds_canonical_tickers(self, db: Database, settings: Settings):
        """Seeded tickers go through the same canonicalization as user input."""
        await create_seeded_user(db, settings, "alice")
        rows = await db.fetch_all("SELECT ticker FROM watchlist")
        assert all(row["ticker"] == row["ticker"].strip().upper() for row in rows)

    async def test_respects_configured_initial_cash(self, db: Database):
        """The starting balance comes from settings, not a hardcoded constant."""
        custom = Settings(initial_cash=250.0)
        await create_seeded_user(db, custom, "alice")
        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'alice'")
        assert profile["cash_balance"] == 250.0
