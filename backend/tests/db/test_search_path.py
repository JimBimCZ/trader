"""A pool can be confined to one Postgres schema.

This is what gives each test its own isolated tables inside one shared
database, and it is the only reason the app knows the word "schema".
"""

from __future__ import annotations

import uuid

import asyncpg

from app.db.postgres import PostgresDatabase, normalize_dsn
from tests.conftest import TEST_DSN


class TestSearchPath:
    async def test_tables_land_in_the_named_schema(self):
        schema = f"probe_{uuid.uuid4().hex[:8]}"
        db = await PostgresDatabase.connect(TEST_DSN, search_path=schema)
        try:
            await db.initialize_schema()
            row = await db.fetch_one(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'users_profile'"
            )
            assert row["table_schema"] == schema
        finally:
            await db.close()
            admin = await asyncpg.connect(normalize_dsn(TEST_DSN))
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    async def test_no_search_path_uses_the_default_schema(self):
        db = await PostgresDatabase.connect(TEST_DSN)
        try:
            row = await db.fetch_one("SELECT current_schema() AS s")
            assert row["s"] == "public"
        finally:
            await db.close()
