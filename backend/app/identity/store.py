"""Reading and writing users_profile.

The only module that writes `kind`. Everything else treats a user as opaque.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from ..clock import utcnow_iso
from ..config import Settings
from ..db import DEFAULT_WATCHLIST, Database, seed_user
from .models import User

logger = logging.getLogger(__name__)

_USER_COLUMNS = "id, cash_balance, kind, created_at, last_seen_at, email, display_name, avatar_url"


def _to_user(row) -> User:
    return User(
        id=row["id"],
        cash_balance=row["cash_balance"],
        kind=row["kind"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
        email=row["email"],
        display_name=row["display_name"],
        avatar_url=row["avatar_url"],
    )


class UserStore:
    """Loads, mints, and expires users."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def get(self, user_id: str) -> User | None:
        row = await self._db.fetch_one(
            f"SELECT {_USER_COLUMNS} FROM users_profile WHERE id = ?",
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
            await seed_user(self._db, self._settings, user_id, demo=self._settings.demo_portfolio)
        logger.info("Minted guest %s", user_id)
        # Re-read rather than construct: the demo seed moves cash_balance, and
        # returning the pre-seed figure would put a stale number in front of
        # the caller that resolves this user.
        minted = await self.get(user_id)
        if minted is None:  # pragma: no cover -- just committed
            raise LookupError(f"Minted a guest that does not exist: {user_id}")
        return minted

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

    async def lookup_identity(self, provider: str, subject: str) -> str | None:
        """The user a provider identity belongs to, or None if it is new.

        The pair is the whole key. Matching on email instead -- or as a
        fallback -- is an account-takeover vector wherever a provider does not
        guarantee the address is verified (D-6).
        """
        row = await self._db.fetch_one(
            "SELECT user_id FROM oauth_identities WHERE provider = ? AND provider_user_id = ?",
            (provider, subject),
        )
        return row["user_id"] if row else None

    async def attach_identity(
        self, user_id: str, provider: str, subject: str, email: str | None
    ) -> None:
        """Link a provider identity to a row.

        ON CONFLICT DO NOTHING rather than an upsert: the pair is already the
        primary key, so a conflict means this identity is linked, and the only
        row it could be linked to is the one the caller just resolved.
        """
        await self._db.execute(
            "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
            "created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (provider, provider_user_id) DO NOTHING",
            (provider, subject, user_id, email, utcnow_iso()),
        )

    async def promote(
        self, user_id: str, email: str | None, name: str | None, avatar: str | None
    ) -> User:
        """Turn a guest row into a signed-in user, in place.

        In place is the whole point: the id does not change, so the cookie
        already in the browser stays valid and every watchlist row, position,
        trade and message follows the user across without being touched.

        COALESCE keeps a previously stored value when a provider returns null
        for a field -- signing in with GitHub after Google should not blank an
        avatar GitHub happens not to expose.
        """
        await self._db.execute(
            "UPDATE users_profile SET kind = 'user', email = COALESCE(?, email), "
            "display_name = COALESCE(?, display_name), avatar_url = COALESCE(?, avatar_url) "
            "WHERE id = ?",
            (email, name, avatar, user_id),
        )
        user = await self.get(user_id)
        if user is None:  # pragma: no cover -- the caller just resolved this row
            raise LookupError(f"Promoted a user that does not exist: {user_id}")
        return user

    async def has_activity(self, user_id: str) -> bool:
        """Whether this user has done anything worth warning about losing.

        Three signals, per the spec: any trade, any chat message, or a
        watchlist that differs from the seeded ten. The watchlist is compared
        by count *and* by membership, because a removal followed by an
        addition leaves the count untouched while the list is no longer the
        one we seeded.

        The common case is an untouched guest, which must not produce a
        prompt -- a warning that fires on every sign-in trains people to
        dismiss it, and the one time it matters they will.

        The unseeded-ticker count binds the default list as a Postgres array
        and checks membership with `<> ALL(...)`, rather than a `NOT IN`
        built from generated placeholders -- confirmed working against
        asyncpg through this wrapper's `?`-rewriting.

        Demo trades do not count. A seeded guest has four of them, and if
        they registered here every guest would look active: the conflict
        dialog would fire on every sign-in, and the demo would never meet the
        "no activity of their own" condition that lets it be cleared.
        """
        row = await self._db.fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM trades WHERE user_id = ? AND NOT is_demo) AS trades,
                (SELECT COUNT(*) FROM chat_messages WHERE user_id = ?) AS messages,
                (SELECT COUNT(*) FROM watchlist WHERE user_id = ?)     AS watched,
                (SELECT COUNT(*) FROM watchlist WHERE user_id = ? AND ticker <> ALL(?))
                                                                       AS unseeded
            """,
            (user_id, user_id, user_id, user_id, list(DEFAULT_WATCHLIST)),
        )
        if row is None:  # pragma: no cover
            return False
        return bool(
            row["trades"]
            or row["messages"]
            or row["unseeded"]
            or row["watched"] != len(DEFAULT_WATCHLIST)
        )


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
