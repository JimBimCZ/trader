"""Chooses the database implementation from configuration."""

from __future__ import annotations

import logging

from ..config import Settings
from .connection import Database, SqliteDatabase, open_connection

logger = logging.getLogger(__name__)


async def open_database(settings: Settings) -> Database:
    """Postgres when `DATABASE_URL` is set, SQLite otherwise.

    Mirrors how the market data source is selected: one environment variable,
    decided once, with the container deployment keeping the simpler option.
    """
    if settings.database_url:
        # Imported here so the container deployment does not need asyncpg, and
        # so the serverless bundle does not need aiosqlite.
        from .postgres import PostgresDatabase

        logger.info("Database: Postgres")
        return await PostgresDatabase.connect(settings.database_url)

    logger.info("Database: SQLite at %s", settings.db_path)
    return SqliteDatabase(await open_connection(settings.db_path))
