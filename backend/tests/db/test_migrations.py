"""The forward-only migration list.

CREATE TABLE IF NOT EXISTS cannot add a column to a table Neon already has,
which is the gap that bites on the second deploy rather than the first. Every
statement here is idempotent, so the list needs no version table.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from app.db import init_db
from app.db.migrations import MIGRATIONS, run_migrations
from app.db.postgres import PostgresDatabase, normalize_dsn
from tests.conftest import create_seeded_user

PER_USER_TABLES = ["watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages"]


class TestIdempotency:
    async def test_running_twice_is_safe(self, db):
        """The second run is what happens on every deploy after the first."""
        await run_migrations(db)
        await run_migrations(db)

    async def test_every_statement_is_individually_repeatable(self, db):
        await run_migrations(db)
        for statement in MIGRATIONS:
            await db.execute(statement)


class TestSeedingSurvivesMigration:
    async def test_a_seeded_user_still_gets_their_watchlist(self, db, settings):
        """Seeding a user before migrating leaves them their full default
        watchlist, not just cash. Migration 001 depends on that order -- it
        adds a foreign key from `watchlist.user_id` to a profile row that must
        already exist."""
        await create_seeded_user(db, settings, "alice")
        await run_migrations(db)

        row = await db.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
        assert row["n"] == 10


class TestForeignKeys:
    @pytest.mark.parametrize("table", PER_USER_TABLES)
    async def test_user_id_references_the_profile(self, db, table):
        await run_migrations(db)
        row = await db.fetch_one(
            """
            SELECT c.confdeltype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE t.relname = ? AND c.contype = 'f' AND n.nspname = current_schema()
            """,
            (table,),
        )
        assert row is not None, f"{table}.user_id has no foreign key"
        # pg_constraint.confdeltype is Postgres's internal one-byte "char" type,
        # which asyncpg 0.31 decodes as bytes rather than str.
        assert row["confdeltype"] == b"c", "the foreign key must cascade on delete"

    async def test_deleting_a_user_removes_their_rows(self, db, settings):
        """This cascade is what makes guest expiry a single DELETE."""
        await create_seeded_user(db, settings, "alice")
        await run_migrations(db)
        before = await db.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
        assert before["n"] == 10

        await db.execute("DELETE FROM users_profile WHERE id = ?", ("alice",))

        after = await db.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
        assert after["n"] == 0


class TestForeignKeyGuardIsSchemaScoped:
    async def test_second_schema_also_gets_the_foreign_key(self, db, settings):
        """Regression: pg_constraint.conname is unique per relation, not per database.

        An existence check that matched on name alone would find `fk_watchlist_user`
        already used by the `db` fixture's schema and skip ADD CONSTRAINT in a second
        schema entirely, leaving its watchlist table with no foreign key at all.
        """
        await run_migrations(db)  # the first schema gets its constraint first

        other_schema = f"test_{uuid.uuid4().hex[:12]}"
        other = await PostgresDatabase.connect(settings.database_url, search_path=other_schema)
        try:
            await init_db(other)
            await run_migrations(other)

            row = await other.fetch_one(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE t.relname = 'watchlist'
                  AND c.conname = 'fk_watchlist_user'
                  AND n.nspname = current_schema()
                """
            )
            assert row is not None, "second schema's watchlist is missing its foreign key"
        finally:
            await other.close()
            admin = await asyncpg.connect(normalize_dsn(settings.database_url))
            try:
                await admin.execute(f'DROP SCHEMA IF EXISTS "{other_schema}" CASCADE')
            finally:
                await admin.close()


class TestMigration002AddsIdentityColumns:
    async def test_kind_and_last_seen_at_exist_after_migrating(self, db):
        await run_migrations(db)

        rows = await db.fetch_all(
            "SELECT column_name, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = 'users_profile' AND table_schema = current_schema()"
        )
        columns = {row["column_name"]: row for row in rows}

        assert "kind" in columns
        assert columns["kind"]["is_nullable"] == "NO"
        assert "guest" in (columns["kind"]["column_default"] or "")
        assert "last_seen_at" in columns
        assert columns["last_seen_at"]["is_nullable"] == "NO"

    async def test_kind_rejects_a_value_outside_the_check(self, db):
        await run_migrations(db)
        await db.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at, last_seen_at) "
            "VALUES (?, ?, ?, ?)",
            ("check-probe", 10000.0, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

        import asyncpg

        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await db.execute(
                "UPDATE users_profile SET kind = 'admin' WHERE id = ?", ("check-probe",)
            )

    async def test_the_kind_seen_index_exists(self, db):
        await run_migrations(db)
        rows = await db.fetch_all(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'users_profile' AND schemaname = current_schema()"
        )
        assert "idx_users_kind_seen" in {row["indexname"] for row in rows}
