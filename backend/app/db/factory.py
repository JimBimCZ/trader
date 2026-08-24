"""Opens the database."""

from __future__ import annotations

import logging

from ..config import Settings
from .postgres import PostgresDatabase

logger = logging.getLogger(__name__)


async def open_database(settings: Settings) -> PostgresDatabase:
    """Connect to Postgres. There is no second option."""
    dsn = settings.require_database_url()
    logger.info("Database: Postgres")
    return await PostgresDatabase.connect(dsn, search_path=settings.db_schema)
