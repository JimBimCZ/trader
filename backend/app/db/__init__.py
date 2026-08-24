"""Database layer: connection, schema, migrations, and seed data.

Public API:
    Database          - the database (Postgres; the alias predates being the only one)
    open_database     - connect, or fail with a clear message
    init_db           - create the schema (idempotent)
    run_migrations    - apply forward-only schema changes (idempotent)
    seed_user         - write cash balance and watchlist for one user
    seed_if_empty     - transitional: seed the shared `default` user
    DEFAULT_USER_ID   - the hardcoded single-user id
    DEFAULT_WATCHLIST - the ten starting tickers
"""

from __future__ import annotations

from .connection import DEFAULT_USER_ID, Database, init_db
from .factory import open_database
from .migrations import run_migrations
from .seed import DEFAULT_WATCHLIST, seed_if_empty, seed_user

__all__ = [
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "Database",
    "init_db",
    "open_database",
    "run_migrations",
    "seed_if_empty",
    "seed_user",
]
