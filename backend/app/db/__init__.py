"""Database layer: connection management, schema, and seed data.

Public API:
    Database          - what the repositories need, whichever backend is behind it
    SqliteDatabase    - the container deployment's implementation
    open_database     - selects Postgres or SQLite from settings
    open_connection   - open and configure the SQLite connection
    init_db           - create the schema (idempotent)
    seed_if_empty     - write default profile and watchlist on a fresh database
    DEFAULT_USER_ID   - the hardcoded single-user id
    DEFAULT_WATCHLIST - the ten starting tickers
"""

from __future__ import annotations

from .connection import (
    DEFAULT_USER_ID,
    Database,
    SqliteDatabase,
    init_db,
    open_connection,
)
from .factory import open_database
from .seed import DEFAULT_WATCHLIST, seed_if_empty

__all__ = [
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "Database",
    "SqliteDatabase",
    "init_db",
    "open_connection",
    "open_database",
    "seed_if_empty",
]
