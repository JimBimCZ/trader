"""Database connection, transactions, and one-time initialization."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from .schema import SCHEMA_SQL

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"


async def open_connection(path: Path) -> aiosqlite.Connection:
    """Open the SQLite database, creating parent directories as needed.

    WAL mode lets readers proceed while a write transaction is open, which is
    what keeps GET routes responsive while a trade commits.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.execute("PRAGMA busy_timeout=5000")
    await conn.commit()
    return conn


class Database(ABC):
    """What the repositories need from a database, whichever one is behind it.

    Two implementations exist: SQLite for the container deployment, Postgres for
    the serverless one, where there is no disk to keep a file on. The interface
    is narrow on purpose — the repositories write plain SQL with `?`
    placeholders, and the Postgres implementation rewrites those rather than
    making every query dialect-aware.
    """

    #: Column that breaks ties between rows sharing a timestamp. SQLite has an
    #: implicit rowid; Postgres has to be given one.
    sequence_column: str = "rowid"

    @abstractmethod
    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None: ...

    @abstractmethod
    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Any | None: ...

    @abstractmethod
    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[Database]:
        """Run a block atomically. Rolls back on any exception."""

    @abstractmethod
    async def initialize_schema(self) -> None:
        """Create the schema if absent. Idempotent."""

    @abstractmethod
    async def close(self) -> None: ...

    async def is_healthy(self) -> bool:
        try:
            await self.fetch_one("SELECT 1")
        except Exception:
            logger.exception("Database health check failed")
            return False
        return True


class SqliteDatabase(Database):
    """Thin wrapper over one shared aiosqlite connection.

    One connection for the whole process: SQLite has a single writer and
    pooling buys nothing here. Business-level atomicity comes from the
    transaction() helper plus the service-level asyncio locks — aiosqlite
    serializes individual statements, but a multi-statement transaction still
    needs the caller to hold a lock across its await points.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @property
    def connection(self) -> aiosqlite.Connection:
        return self._conn

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self._conn.execute(sql, params)

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self._conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def commit(self) -> None:
        await self._conn.commit()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        """Run a block atomically. Rolls back on any exception.

        BEGIN IMMEDIATE takes the write lock up front rather than on first
        write, so a conflict surfaces at the start instead of mid-transaction.
        """
        await self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except Exception:
            await self._conn.rollback()
            raise
        else:
            await self._conn.commit()

    async def initialize_schema(self) -> None:
        await self._conn.executescript(SCHEMA_SQL)
        await self.commit()
        logger.info("SQLite schema ready")

    async def close(self) -> None:
        await self._conn.close()


async def init_db(db: Database) -> None:
    """Create the schema if absent. Idempotent, safe on every startup."""
    await db.initialize_schema()
