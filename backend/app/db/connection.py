"""Database initialization and the shared user id.

One implementation remains: `PostgresDatabase`. `Database` is kept as a name
so the repositories' type hints read as an intent ("a database") rather than
as a dependency on asyncpg, but it is no longer an abstraction with a second
implementation behind it.
"""

from __future__ import annotations

import logging

from .postgres import PostgresDatabase

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"

#: The only implementation. Kept as an alias so call sites read clearly.
Database = PostgresDatabase


async def init_db(db: Database) -> None:
    """Create the schema if absent. Idempotent, safe on every startup."""
    await db.initialize_schema()
