"""Default seed data, written once when the database is empty."""

from __future__ import annotations

import logging
import uuid

from ..clock import utcnow_iso
from ..config import Settings
from ..market.tickers import canonicalize_ticker
from .connection import DEFAULT_USER_ID, Database

logger = logging.getLogger(__name__)

#: The ten tickers a fresh install starts watching.
DEFAULT_WATCHLIST = [
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
]


async def seed_if_empty(db: Database, settings: Settings) -> bool:
    """Seed the default profile and watchlist if no profile exists.

    Returns True if seeding happened. Safe to call on every startup.
    """
    existing = await db.fetch_one("SELECT id FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,))
    if existing is not None:
        return False

    now = utcnow_iso()
    async with db.transaction():
        await db.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_ID, settings.initial_cash, now),
        )
        for ticker in DEFAULT_WATCHLIST:
            await db.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER_ID, canonicalize_ticker(ticker), now),
            )

    logger.info("Seeded default profile and %d watchlist tickers", len(DEFAULT_WATCHLIST))
    return True
