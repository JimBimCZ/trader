"""Default seed data, written once per user."""

from __future__ import annotations

import logging
import uuid

from ..clock import utcnow_iso
from ..config import Settings
from ..market.tickers import canonicalize_ticker
from .connection import Database

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
    """Give one user the default watchlist and a snapshot at t=0.

    The profile row must already exist -- the watchlist rows carry a foreign
    key to it, and it is where the starting cash balance is written. Callers
    create the row and seed inside one transaction.

    Per user, not per database. The single-user form of this asked "is the
    database empty?", which with many users is false the moment the first
    guest exists -- so it would have silently skipped seeding everyone after
    them.

    The snapshot is what stops a brand-new user's P&L chart from being empty
    until the writer's next tick. Startup used to leave one behind for the
    single seeded user; with users minted on demand it belongs here, where
    both minting and reset go through it.
    """
    now = utcnow_iso()
    for ticker in DEFAULT_WATCHLIST:
        await db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, ticker) DO NOTHING",
            (str(uuid.uuid4()), user_id, canonicalize_ticker(ticker), now),
        )
    # Guarded the way the watchlist inserts are, so the whole function is
    # idempotent: a re-seed that repaired missing rows would otherwise inject
    # a second `initial_cash` point, dated today, into a chart that has moved
    # on since. Reset deletes this user's snapshots inside the same
    # transaction, so it still gets its fresh t=0 point.
    await db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "SELECT ?, ?, ?, ? "
        "WHERE NOT EXISTS (SELECT 1 FROM portfolio_snapshots WHERE user_id = ?)",
        (str(uuid.uuid4()), user_id, settings.initial_cash, now, user_id),
    )
    logger.info("Seeded %d watchlist tickers for %s", len(DEFAULT_WATCHLIST), user_id)
