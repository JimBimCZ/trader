"""Tests for database connection, transactions, and initialization."""

from __future__ import annotations

import pytest

from app.db import Database, init_db, open_connection


class TestOpenConnection:
    async def test_creates_parent_directories(self, tmp_path):
        """The database file's directory is created if it does not exist."""
        path = tmp_path / "nested" / "deeper" / "trader.db"
        conn = await open_connection(path)
        try:
            assert path.exists()
        finally:
            await conn.close()

    async def test_enables_wal_mode(self, tmp_path):
        """WAL mode is on, so readers are not blocked by an open write."""
        conn = await open_connection(tmp_path / "t.db")
        try:
            async with conn.execute("PRAGMA journal_mode") as cursor:
                row = await cursor.fetchone()
            assert row[0].lower() == "wal"
        finally:
            await conn.close()


class TestInitDb:
    async def test_creates_every_table(self, db: Database):
        """All six tables from the schema exist after init."""
        rows = await db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row["name"] for row in rows}
        assert {
            "users_profile",
            "watchlist",
            "positions",
            "trades",
            "portfolio_snapshots",
            "chat_messages",
        } <= names

    async def test_is_idempotent(self, db: Database):
        """Running init twice does not fail or duplicate anything."""
        await init_db(db)
        await init_db(db)
        rows = await db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
        assert len([r for r in rows if r["name"] == "positions"]) == 1

    async def test_side_check_constraint(self, db: Database):
        """The trades table rejects a side other than buy or sell."""
        import aiosqlite

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
                " VALUES ('1', 'default', 'AAPL', 'hold', 1, 1, 'now')"
            )


class TestTransaction:
    async def test_commits_on_success(self, db: Database):
        """Work inside a transaction persists once the block exits cleanly."""
        async with db.transaction():
            await db.execute(
                "INSERT INTO users_profile (id, cash_balance, created_at)"
                " VALUES ('default', 10000.0, 'now')"
            )
        row = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'default'")
        assert row["cash_balance"] == 10000.0

    async def test_rolls_back_on_exception(self, db: Database):
        """A failure part-way through leaves no partial write behind."""
        with pytest.raises(RuntimeError):
            async with db.transaction():
                await db.execute(
                    "INSERT INTO users_profile (id, cash_balance, created_at)"
                    " VALUES ('default', 10000.0, 'now')"
                )
                raise RuntimeError("boom")
        row = await db.fetch_one("SELECT id FROM users_profile WHERE id = 'default'")
        assert row is None


class TestIsHealthy:
    async def test_reports_healthy(self, db: Database):
        """A live connection reports healthy."""
        assert await db.is_healthy() is True

    async def test_reports_unhealthy_after_close(self, db: Database):
        """A closed connection reports unhealthy rather than raising."""
        await db.connection.close()
        assert await db.is_healthy() is False
