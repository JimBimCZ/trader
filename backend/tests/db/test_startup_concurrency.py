"""Regression coverage for Important #2: concurrent cold starts used to race.

`init_db`, `seed_if_empty`, and `run_migrations` are each a check-then-act
step (`CREATE TABLE IF NOT EXISTS`, a SELECT-then-INSERT, and an
existence-checked `ADD CONSTRAINT`) with no atomicity across the three.
Two instances of the app starting at once -- the normal case on a platform
that starts more than one invocation concurrently -- used to race them:
`main.py`'s lifespan now wraps the sequence in `db.transaction()`, which
takes the cross-instance advisory lock for its whole duration and serializes
the second instance behind the first instead of letting both run the same
check-then-act step at once.

This test exercises exactly that wrapped sequence with two independent
`PostgresDatabase` connections against one shared schema, run concurrently
via `asyncio.gather`. It is not a timing test: the lock makes the outcome
correct regardless of which instance the event loop happens to schedule
first, so there is no race window to get lucky or unlucky on -- which is
what makes it safe to run in CI rather than a sleep-based reproduction of
the report's `asyncio.Barrier` probe.
"""

from __future__ import annotations

import asyncio
import uuid

from app.config import Settings
from app.db import init_db, run_migrations, seed_if_empty
from app.db.postgres import PostgresDatabase
from tests.conftest import TEST_DSN, _drop_schema


async def _start(schema: str, settings: Settings) -> None:
    """Mirrors main.py's lifespan: open a pool, then run the wrapped sequence."""
    db = await PostgresDatabase.connect(TEST_DSN, search_path=schema)
    try:
        async with db.transaction():
            await init_db(db)
            await seed_if_empty(db, settings)
            await run_migrations(db)
    finally:
        await db.close()


class TestConcurrentStartupIsSerialized:
    async def test_two_instances_starting_at_once_do_not_race(self):
        schema = f"test_{uuid.uuid4().hex[:12]}"
        settings = Settings(database_url=TEST_DSN, db_schema=schema, initial_cash=10_000.0)

        try:
            results = await asyncio.gather(
                _start(schema, settings), _start(schema, settings), return_exceptions=True
            )
            failures = [r for r in results if isinstance(r, BaseException)]
            assert not failures, f"concurrent startup raised: {failures!r}"

            admin = await PostgresDatabase.connect(TEST_DSN, search_path=schema)
            try:
                profiles = await admin.fetch_one("SELECT COUNT(*) AS n FROM users_profile")
                watchlist = await admin.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
                # Exactly one profile and one full watchlist, not two of
                # either -- proof the second instance saw the first's
                # committed seed rather than racing its own SELECT-then-INSERT.
                assert profiles["n"] == 1
                assert watchlist["n"] == 10
            finally:
                await admin.close()
        finally:
            await _drop_schema(TEST_DSN, schema)
