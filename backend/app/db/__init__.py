"""Database layer: connection, schema, migrations, and seed data.

Public API:
    Database          - the database (Postgres; the alias predates being the only one)
    open_database     - connect, or fail with a clear message
    init_db           - create the schema (idempotent)
    run_migrations    - apply forward-only schema changes (idempotent)
    seed_user         - write the default watchlist for one user
    DEFAULT_WATCHLIST - the ten starting tickers
    DEMO_HOLDINGS     - the four positions a demo guest opens on
"""

from __future__ import annotations

from .connection import Database, init_db
from .factory import open_database
from .migrations import run_migrations
from .seed import DEFAULT_WATCHLIST, DEMO_HOLDINGS, seed_user

__all__ = [
    "DEFAULT_WATCHLIST",
    "DEMO_HOLDINGS",
    "Database",
    "init_db",
    "open_database",
    "run_migrations",
    "seed_user",
]
