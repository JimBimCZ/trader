"""The Postgres implementation of `Database`.

The repositories write plain SQL with `?` placeholders, which asyncpg does
not accept; `_to_numbered` rewrites those into `$1, $2, …` on the way
through, so this is the only file that knows a translation happens.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import asyncpg

from .schema import SCHEMA_SQL

logger = logging.getLogger(__name__)

#: Serialises every write transaction across every instance. A per-process
#: asyncio.Lock cannot do that, and two instances are the normal case here.
_WRITE_LOCK_KEY = 0x7472_6472  # "trdr"

#: Query-string parameters that appear in a Neon connection string and that
#: asyncpg rejects rather than ignores.
_UNSUPPORTED_DSN_PARAMS = ("channel_binding",)

#: The active transaction's connection, so every statement inside one
#: `transaction()` block lands on the same pooled connection.
_current: ContextVar[asyncpg.Connection | None] = ContextVar("pg_connection", default=None)


def _to_numbered(sql: str) -> str:
    """Rewrite `?` placeholders as `$1, $2, …`, leaving string literals alone."""
    out: list[str] = []
    index = 0
    in_literal = False
    for char in sql:
        if char == "'":
            in_literal = not in_literal
            out.append(char)
        elif char == "?" and not in_literal:
            index += 1
            out.append(f"${index}")
        else:
            out.append(char)
    return "".join(out)


def normalize_dsn(dsn: str) -> str:
    """Make a Neon connection string acceptable to asyncpg.

    Neon hands out `postgresql://…?sslmode=require&channel_binding=require`.
    asyncpg understands `sslmode` but raises on `channel_binding`, so the
    parameters it does not know are dropped rather than passed through.
    """
    for param in _UNSUPPORTED_DSN_PARAMS:
        dsn = re.sub(rf"[?&]{param}=[^&]*", "", dsn)
    # Removing the first parameter can leave the separators wrong.
    if "?" not in dsn and "&" in dsn:
        dsn = dsn.replace("&", "?", 1)
    return dsn


class PostgresDatabase:
    """A database over an asyncpg pool."""

    def __init__(self, pool: asyncpg.Pool, search_path: str = "") -> None:
        self._pool = pool
        self._search_path = search_path

    @classmethod
    async def connect(cls, dsn: str, max_size: int = 4, search_path: str = "") -> PostgresDatabase:
        """Open a pool against Neon's pooled endpoint.

        `statement_cache_size=0` is not optional: the pooled endpoint runs
        pgbouncer in transaction mode, where a prepared statement made on one
        server-side connection is not there on the next, and asyncpg's cache
        would hand out stale statement names.

        `search_path` confines every table to one schema. Production leaves it
        empty and uses `public`; the test suite gives each test its own schema,
        which is what makes them isolated and safe to run in parallel.
        """
        pool = await asyncpg.create_pool(
            normalize_dsn(dsn),
            min_size=0,
            max_size=max_size,
            statement_cache_size=0,
            command_timeout=15.0,
            server_settings={"search_path": search_path} if search_path else None,
        )
        logger.info("Postgres pool ready")
        return cls(pool, search_path)

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[asyncpg.Connection]:
        """The transaction's connection if one is open, otherwise a fresh one."""
        existing = _current.get()
        if existing is not None:
            yield existing
            return
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self._connection() as conn:
            await conn.execute(_to_numbered(sql), *params)

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> asyncpg.Record | None:
        async with self._connection() as conn:
            return await conn.fetchrow(_to_numbered(sql), *params)

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[asyncpg.Record]:
        async with self._connection() as conn:
            return list(await conn.fetch(_to_numbered(sql), *params))

    async def commit(self) -> None:
        """No-op: statements outside `transaction()` autocommit."""

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[PostgresDatabase]:
        """Run a block atomically, holding the cross-instance write lock.

        The advisory lock is taken inside the transaction and released with it,
        which is what replaces the per-process `asyncio.Lock` the services hold:
        that one cannot see the other instances a serverless deployment will
        happily start.
        """
        if _current.get() is not None:
            # Already inside a transaction; nesting would deadlock on the lock.
            yield self
            return

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock($1)", _WRITE_LOCK_KEY)
                token = _current.set(conn)
                try:
                    yield self
                finally:
                    _current.reset(token)

    async def initialize_schema(self) -> None:
        # Goes through _connection(), not a fresh acquire, so a caller that
        # wraps this in transaction() gets schema creation on the same
        # connection -- and under the same advisory lock -- as whatever runs
        # after it. Outside a transaction() block this is unchanged: one
        # connection borrowed from the pool for the duration of the call.
        async with self._connection() as conn:
            if self._search_path:
                # The pool's search_path names it, but naming a schema does not
                # create it, and CREATE TABLE will not create it either.
                #
                # Belt-and-braces, not a live fix: an embedded `"` here could
                # break out of the quoted identifier, but self._search_path is
                # also passed as server_settings={"search_path": ...} at
                # connect() above, and asyncpg validates that value -- as
                # search_path list syntax -- before this method ever runs, so
                # every payload that would inject here is already rejected
                # earlier. Escaping it anyway costs nothing and doesn't rely
                # on that other validation staying in place.
                escaped = self._search_path.replace('"', '""')
                await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{escaped}"')
            await conn.execute(SCHEMA_SQL)
        logger.info("Postgres schema ready")

    async def close(self) -> None:
        await self._pool.close()

    async def is_healthy(self) -> bool:
        try:
            await self.fetch_one("SELECT 1")
        except Exception:
            logger.exception("Database health check failed")
            return False
        return True
