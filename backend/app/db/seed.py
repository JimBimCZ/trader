"""Default seed data, written once per user."""

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


async def seed_user(db: Database, settings: Settings, user_id: str) -> None:
    """Give one user their starting cash balance and the default watchlist.

    The profile row must already exist -- the watchlist rows carry a foreign
    key to it. Callers create the row and seed inside one transaction.

    This replaces seed_if_empty, whose "is the database empty?" question was
    the single-user form of "does this user have rows?". With many users the
    database is never empty after the first guest, so that check would have
    silently skipped seeding for everyone after the first.
    """
    now = utcnow_iso()
    for ticker in DEFAULT_WATCHLIST:
        await db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, ticker) DO NOTHING",
            (str(uuid.uuid4()), user_id, canonicalize_ticker(ticker), now),
        )
    logger.info("Seeded %d watchlist tickers for %s", len(DEFAULT_WATCHLIST), user_id)


async def seed_if_empty(db: Database, settings: Settings) -> bool:
    """Seed the shared `default` user if it does not exist yet.

    Transitional: kept only so the lifespan and ResetService keep working
    while per-request scoping is built. Task 6 deletes it along with
    DEFAULT_USER_ID.
    """
    existing = await db.fetch_one("SELECT id FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,))
    if existing is not None:
        return False
    now = utcnow_iso()
    async with db.transaction():
        await db.execute(
            "INSERT INTO users_profile "
            "(id, cash_balance, created_at, kind, last_seen_at) "
            "VALUES (?, ?, ?, 'guest', ?)",
            (DEFAULT_USER_ID, settings.initial_cash, now, now),
        )
        await seed_user(db, settings, DEFAULT_USER_ID)
    return True
