"""Regression coverage for the schema-leak fix in tests/conftest.py.

Before this, the `db` and `api_client` fixtures only dropped their throwaway
schema on the path that reached `yield`; a setup failure left it behind
forever, and a run that crashed mid-suite poisoned every run after it (26
orphaned `test_*` schemas were found flaking test_search_path.py). Proving
the fix through pytest's own fixture machinery would mean forcing `init_db`
or `TestClient.__enter__` to fail from outside the fixture, which pytest
does not offer a hook for -- so this exercises the factored-out helpers
(`_provisioned_schema`, `sweep_orphaned_test_schemas`) directly instead.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from app.db import init_db
from app.db.postgres import normalize_dsn
from tests.conftest import TEST_DSN, _provisioned_schema, sweep_orphaned_test_schemas


async def _schema_exists(schema: str) -> bool:
    admin = await asyncpg.connect(normalize_dsn(TEST_DSN))
    try:
        row = await admin.fetchrow(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = $1", schema
        )
        return row is not None
    finally:
        await admin.close()


class TestProvisionedSchemaCleansUpOnFailure:
    async def test_a_failure_after_init_db_still_drops_the_schema(self):
        """Mirrors the `db` fixture's body: connect, init_db, then something
        raises before the fixture would have reached `yield`."""
        schema = f"test_{uuid.uuid4().hex[:12]}"

        with pytest.raises(RuntimeError, match="simulated setup failure"):
            async with _provisioned_schema(TEST_DSN, schema) as database:
                await init_db(database)  # this is what actually creates the schema
                raise RuntimeError("simulated setup failure")

        assert not await _schema_exists(schema), "schema leaked despite the setup failure"

    async def test_a_failure_inside_init_db_itself_still_drops_the_schema(self):
        """The narrower case the finding calls out by name: the exception
        originates inside init_db, not in caller code after it."""
        schema = f"test_{uuid.uuid4().hex[:12]}"

        class _BoomDatabase:
            """Creates the schema for real, then blows up like a broken migration."""

            def __init__(self, real):
                self._real = real

            async def initialize_schema(self) -> None:
                await self._real.initialize_schema()  # schema now exists in Postgres
                raise RuntimeError("simulated init_db failure")

        with pytest.raises(RuntimeError, match="simulated init_db failure"):
            async with _provisioned_schema(TEST_DSN, schema) as database:
                await init_db(_BoomDatabase(database))

        assert not await _schema_exists(schema), "schema leaked despite the init_db failure"

    async def test_the_happy_path_still_leaves_nothing_behind(self):
        """Sanity check that the fix didn't just make cleanup unconditional
        in a way that breaks the normal, no-error case."""
        schema = f"test_{uuid.uuid4().hex[:12]}"

        async with _provisioned_schema(TEST_DSN, schema) as database:
            await init_db(database)

        assert not await _schema_exists(schema)


class TestSweepIsScopedToTestSchemas:
    async def test_sweep_drops_a_matching_orphan(self):
        schema = f"test_{uuid.uuid4().hex[:12]}"
        admin = await asyncpg.connect(normalize_dsn(TEST_DSN))
        try:
            await admin.execute(f'CREATE SCHEMA "{schema}"')
        finally:
            await admin.close()

        dropped = await sweep_orphaned_test_schemas(TEST_DSN)

        assert schema in dropped
        assert not await _schema_exists(schema)

    async def test_sweep_never_touches_public_or_a_lookalike_schema(self):
        """The one genuinely dangerous thing in this batch: a loose pattern
        on a DROP SCHEMA CASCADE could destroy application data. `public`
        and near-miss names (wrong length, wrong prefix, uppercase hex) must
        all survive a sweep untouched."""
        lookalikes = [
            "public",
            "test_short",  # too few hex characters
            "test_" + "a" * 13,  # one too many
            "test_" + "G" * 12,  # not hex
            "testing_" + uuid.uuid4().hex[:12],  # wrong prefix entirely
        ]
        admin = await asyncpg.connect(normalize_dsn(TEST_DSN))
        try:
            for name in lookalikes:
                if name != "public":
                    await admin.execute(f'CREATE SCHEMA IF NOT EXISTS "{name}"')
            existing_before = {
                r["schema_name"]
                for r in await admin.fetch("SELECT schema_name FROM information_schema.schemata")
            }
        finally:
            await admin.close()

        dropped = await sweep_orphaned_test_schemas(TEST_DSN)

        assert set(dropped).isdisjoint(lookalikes)

        admin = await asyncpg.connect(normalize_dsn(TEST_DSN))
        try:
            existing_after = {
                r["schema_name"]
                for r in await admin.fetch("SELECT schema_name FROM information_schema.schemata")
            }
            for name in lookalikes:
                await admin.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
        finally:
            await admin.close()

        assert existing_before & set(lookalikes) == existing_after & set(lookalikes)
