"""Data access for the watchlist."""

from __future__ import annotations

import uuid

from ..clock import utcnow_iso
from ..db import DEFAULT_USER_ID, Database


class WatchlistRepository:
    """Tickers the user is watching, ordered by when they were added."""

    def __init__(self, db: Database, user_id: str = DEFAULT_USER_ID) -> None:
        self._db = db
        self._user_id = user_id

    async def list(self) -> list[str]:
        """Watched tickers, oldest first. The frontend renders in this order."""
        rows = await self._db.fetch_all(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (self._user_id,),
        )
        return [row["ticker"] for row in rows]

    async def contains(self, ticker: str) -> bool:
        row = await self._db.fetch_one(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (self._user_id, ticker)
        )
        return row is not None

    async def count(self) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n FROM watchlist WHERE user_id = ?", (self._user_id,)
        )
        return int(row["n"]) if row else 0

    async def add(self, ticker: str) -> None:
        """Insert a ticker, ignoring a duplicate. Add is idempotent."""
        await self._db.execute(
            """
            INSERT INTO watchlist (id, user_id, ticker, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id, ticker) DO NOTHING
            """,
            (str(uuid.uuid4()), self._user_id, ticker, utcnow_iso()),
        )

    async def remove(self, ticker: str) -> None:
        await self._db.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (self._user_id, ticker)
        )

    async def delete_all(self) -> None:
        await self._db.execute("DELETE FROM watchlist WHERE user_id = ?", (self._user_id,))
