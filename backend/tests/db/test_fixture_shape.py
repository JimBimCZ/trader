"""The fixtures must hand tests the schema production actually runs.

Without this, a write that violates a foreign key passes the whole suite and
500s in production -- the tests would be asserting against a shape that
exists nowhere else.
"""

from __future__ import annotations

import pytest

EXPECTED_FKS = {
    "fk_watchlist_user",
    "fk_positions_user",
    "fk_trades_user",
    "fk_portfolio_snapshots_user",
    "fk_chat_messages_user",
    "fk_oauth_identities_user",
}


class TestSeededDbIsMigrated:
    async def test_every_per_user_table_has_its_foreign_key(self, seeded_db):
        rows = await seeded_db.fetch_all(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE c.contype = 'f' AND n.nspname = current_schema()"
        )
        assert {row["conname"] for row in rows} == EXPECTED_FKS

    async def test_the_foreign_key_is_actually_enforced(self, seeded_db):
        """A constraint that exists but is NOT VALID would pass the check above."""
        import asyncpg

        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await seeded_db.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                ("probe-row", "no-such-user", "AAPL", "2026-01-01T00:00:00Z"),
            )
