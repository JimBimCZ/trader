"""Database layer: connection management, schema, and seed data.

Public API:
    Database          - connection wrapper with a transaction() helper
    open_connection   - open and configure the SQLite connection
    init_db           - create the schema (idempotent)
    seed_if_empty     - write default profile and watchlist on a fresh database
    DEFAULT_USER_ID   - the hardcoded single-user id
    DEFAULT_WATCHLIST - the ten starting tickers
"""

from __future__ import annotations

from .connection import DEFAULT_USER_ID, Database, init_db, open_connection
from .seed import DEFAULT_WATCHLIST, seed_if_empty

__all__ = [
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "Database",
    "init_db",
    "open_connection",
    "seed_if_empty",
]
