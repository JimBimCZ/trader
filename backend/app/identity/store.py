"""Reading and writing users_profile.

The only module that writes `kind`. Everything else treats a user as opaque.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from ..clock import utcnow_iso
from ..config import Settings
from ..db import Database, seed_user
from .models import User

logger = logging.getLogger(__name__)


def _to_user(row) -> User:
    return User(
        id=row["id"],
        cash_balance=row["cash_balance"],
        kind=row["kind"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )


class UserStore:
    """Loads, mints, and expires users."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def get(self, user_id: str) -> User | None:
        row = await self._db.fetch_one(
            "SELECT id, cash_balance, kind, created_at, last_seen_at "
            "FROM users_profile WHERE id = ?",
            (user_id,),
        )
        return _to_user(row) if row is not None else None

    async def mint_guest(self) -> User:
        """Create a guest and seed it, atomically.

        One transaction: a profile row without its watchlist would be a user
        staring at an empty app, and the watchlist rows carry a foreign key to
        the profile, so the order inside is fixed.
        """
        user_id = f"guest_{uuid.uuid4().hex}"
        now = utcnow_iso()
        async with self._db.transaction():
            await self._db.execute(
                "INSERT INTO users_profile "
                "(id, cash_balance, created_at, kind, last_seen_at) "
                "VALUES (?, ?, ?, 'guest', ?)",
                (user_id, self._settings.initial_cash, now, now),
            )
            await seed_user(self._db, self._settings, user_id)
        logger.info("Minted guest %s", user_id)
        return User(
            id=user_id,
            cash_balance=self._settings.initial_cash,
            kind="guest",
            created_at=now,
            last_seen_at=now,
        )

    async def touch(self, user: User) -> None:
        """Refresh last_seen_at, at most once per throttle window.

        Written on every request this turns each GET into a write, which on
        Neon is a network round trip per read.
        """
        now = utcnow_iso()
        if _seconds_between(user.last_seen_at, now) < self._settings.last_seen_throttle_seconds:
            return
        await self._db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?", (now, user.id)
        )

    async def list_active_since(self, iso_cutoff: str) -> list[str]:
        rows = await self._db.fetch_all(
            "SELECT id FROM users_profile WHERE last_seen_at >= ?", (iso_cutoff,)
        )
        return [row["id"] for row in rows]

    async def delete_expired_guests(self, iso_cutoff: str) -> int:
        """Delete idle guests. The foreign keys cascade the rest away.

        Only guests: a signed-in user never expires.
        """
        rows = await self._db.fetch_all(
            "DELETE FROM users_profile WHERE kind = 'guest' AND last_seen_at < ? RETURNING id",
            (iso_cutoff,),
        )
        if rows:
            logger.info("Deleted %d expired guests", len(rows))
        return len(rows)


def _seconds_between(earlier_iso: str, later_iso: str) -> float:
    """Elapsed seconds, treating an unparseable timestamp as 'long ago'.

    A row written before last_seen_at existed carries the backfilled
    created_at; anything genuinely unreadable should cause a write, not a
    crash on the hottest path in the app.
    """
    try:
        earlier = datetime.fromisoformat(earlier_iso)
        later = datetime.fromisoformat(later_iso)
    except (TypeError, ValueError):
        return float("inf")
    return (later - earlier).total_seconds()
