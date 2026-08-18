"""Data access for profile, positions, trades, and snapshots."""

from __future__ import annotations

import uuid

from ..clock import utcnow_iso
from ..db import DEFAULT_USER_ID, Database
from .models import EPSILON, PortfolioSnapshot, Position, Side, Trade


class UserRepository:
    """The single user profile row: cash balance."""

    def __init__(self, db: Database, user_id: str = DEFAULT_USER_ID) -> None:
        self._db = db
        self._user_id = user_id

    async def get_cash(self) -> float:
        row = await self._db.fetch_one(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (self._user_id,)
        )
        return float(row["cash_balance"]) if row else 0.0

    async def set_cash(self, cash: float) -> None:
        await self._db.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, self._user_id)
        )


class PositionRepository:
    """Open holdings. A projection of the trades log, maintained on write."""

    def __init__(self, db: Database, user_id: str = DEFAULT_USER_ID) -> None:
        self._db = db
        self._user_id = user_id

    @staticmethod
    def _to_position(row) -> Position:
        return Position(
            ticker=row["ticker"], quantity=float(row["quantity"]), avg_cost=float(row["avg_cost"])
        )

    async def get(self, ticker: str) -> Position | None:
        row = await self._db.fetch_one(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (self._user_id, ticker),
        )
        return self._to_position(row) if row else None

    async def list(self) -> list[Position]:
        rows = await self._db.fetch_all(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
            (self._user_id,),
        )
        return [self._to_position(row) for row in rows]

    async def list_open_tickers(self) -> list[str]:
        """Tickers with a non-zero holding. Half of the tracked-ticker union."""
        rows = await self._db.fetch_all(
            "SELECT ticker FROM positions WHERE user_id = ? AND quantity > ? ORDER BY ticker",
            (self._user_id, EPSILON),
        )
        return [row["ticker"] for row in rows]

    async def upsert(self, ticker: str, quantity: float, avg_cost: float) -> None:
        await self._db.execute(
            """
            INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, ticker)
            DO UPDATE SET quantity = excluded.quantity,
                          avg_cost = excluded.avg_cost,
                          updated_at = excluded.updated_at
            """,
            (str(uuid.uuid4()), self._user_id, ticker, quantity, avg_cost, utcnow_iso()),
        )

    async def delete(self, ticker: str) -> None:
        await self._db.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (self._user_id, ticker)
        )

    async def delete_all(self) -> None:
        await self._db.execute("DELETE FROM positions WHERE user_id = ?", (self._user_id,))


class TradeRepository:
    """Append-only trade log. Authoritative; positions and cash derive from it."""

    def __init__(self, db: Database, user_id: str = DEFAULT_USER_ID) -> None:
        self._db = db
        self._user_id = user_id

    async def insert(self, ticker: str, side: Side, quantity: float, price: float) -> Trade:
        trade = Trade(
            id=str(uuid.uuid4()),
            ticker=ticker,
            side=side,
            quantity=quantity,
            price=price,
            executed_at=utcnow_iso(),
        )
        await self._db.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.id,
                self._user_id,
                trade.ticker,
                trade.side,
                trade.quantity,
                trade.price,
                trade.executed_at,
            ),
        )
        return trade

    async def list_recent(self, limit: int = 50) -> list[Trade]:
        rows = await self._db.fetch_all(
            """
            SELECT id, ticker, side, quantity, price, executed_at
            FROM trades WHERE user_id = ?
            ORDER BY executed_at DESC, rowid DESC
            LIMIT ?
            """,
            (self._user_id, limit),
        )
        return [
            Trade(
                id=row["id"],
                ticker=row["ticker"],
                side=row["side"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                executed_at=row["executed_at"],
            )
            for row in rows
        ]

    async def delete_all(self) -> None:
        await self._db.execute("DELETE FROM trades WHERE user_id = ?", (self._user_id,))


class SnapshotRepository:
    """Portfolio value over time, for the P&L chart."""

    def __init__(self, db: Database, user_id: str = DEFAULT_USER_ID) -> None:
        self._db = db
        self._user_id = user_id

    async def insert(self, total_value: float) -> None:
        await self._db.execute(
            """
            INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), self._user_id, total_value, utcnow_iso()),
        )

    async def list(self, limit: int = 500) -> list[PortfolioSnapshot]:
        """Newest `limit` snapshots, returned oldest-first for charting."""
        rows = await self._db.fetch_all(
            """
            SELECT total_value, recorded_at FROM portfolio_snapshots
            WHERE user_id = ?
            ORDER BY recorded_at DESC, rowid DESC
            LIMIT ?
            """,
            (self._user_id, limit),
        )
        return [
            PortfolioSnapshot(total_value=float(r["total_value"]), recorded_at=r["recorded_at"])
            for r in reversed(rows)
        ]

    async def count(self) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) AS n FROM portfolio_snapshots WHERE user_id = ?", (self._user_id,)
        )
        return int(row["n"]) if row else 0

    async def prune_older_than(self, cutoff_iso: str) -> int:
        """Delete snapshots older than the cutoff. Returns rows removed."""
        before = await self.count()
        await self._db.execute(
            "DELETE FROM portfolio_snapshots WHERE user_id = ? AND recorded_at < ?",
            (self._user_id, cutoff_iso),
        )
        return before - await self.count()

    async def delete_all(self) -> None:
        await self._db.execute(
            "DELETE FROM portfolio_snapshots WHERE user_id = ?", (self._user_id,)
        )
