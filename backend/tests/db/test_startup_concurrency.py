"""Regression coverage for Important #2: concurrent cold starts used to race.

`init_db` and `run_migrations` are each a check-then-act step
(`CREATE TABLE IF NOT EXISTS` and an existence-checked `ADD CONSTRAINT`) with
no atomicity across the two. Two instances of the app starting at once -- the
normal case on a platform that starts more than one invocation concurrently
-- used to race them: `main.py`'s lifespan now wraps the sequence in
`db.transaction()`, which takes the cross-instance advisory lock for its whole
duration and serializes the second instance behind the first instead of
letting both run the same check-then-act step at once.

Startup no longer seeds anything -- a fresh database has no users until the
first request mints one -- so the SELECT-then-INSERT that was the third racing
step is gone. `UserStore.mint_guest` is the concurrent-write path now, and it
inserts under a primary key rather than checking first.

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
from app.db import init_db, run_migrations
from app.db.postgres import PostgresDatabase
from tests.conftest import TEST_DSN, _drop_schema, create_seeded_user


async def _start(schema: str) -> None:
    """Mirrors main.py's lifespan: open a pool, then run the wrapped sequence."""
    db = await PostgresDatabase.connect(TEST_DSN, search_path=schema)
    try:
        async with db.transaction():
            await init_db(db)
            await run_migrations(db)
    finally:
        await db.close()


class TestConcurrentStartupIsSerialized:
    async def test_two_instances_starting_at_once_do_not_race(self):
        schema = f"test_{uuid.uuid4().hex[:12]}"
        settings = Settings(database_url=TEST_DSN, db_schema=schema, initial_cash=10_000.0)

        try:
            results = await asyncio.gather(_start(schema), _start(schema), return_exceptions=True)
            failures = [r for r in results if isinstance(r, BaseException)]
            assert not failures, f"concurrent startup raised: {failures!r}"

            admin = await PostgresDatabase.connect(TEST_DSN, search_path=schema)
            try:
                # Both instances ran the same migration; exactly one set of
                # foreign keys exists, and a user seeded through the store
                # lands cleanly on top of it -- proof the second instance
                # waited rather than re-adding a constraint that was already
                # halfway there.
                constraints = await admin.fetch_one(
                    "SELECT COUNT(*) AS n FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace "
                    "WHERE c.contype = 'f' AND n.nspname = current_schema()"
                )
                assert constraints["n"] == 6

                await create_seeded_user(admin, settings, "alice")
                watchlist = await admin.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
                assert watchlist["n"] == 10
            finally:
                await admin.close()
        finally:
            await _drop_schema(TEST_DSN, schema)
