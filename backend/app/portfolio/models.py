"""Portfolio domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["buy", "sell"]

#: Quantities below this are treated as zero. Prevents float dust positions
#: surviving a full liquidation.
EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class Position:
    """An open holding. avg_cost is the weighted average purchase price."""

    ticker: str
    quantity: float
    avg_cost: float

    def to_dict(self) -> dict:
        return {"ticker": self.ticker, "quantity": self.quantity, "avg_cost": self.avg_cost}


@dataclass(frozen=True, slots=True)
class ValuedPosition:
    """A position priced against the live cache, for API responses."""

    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    pct_change: float

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "pct_change": self.pct_change,
        }


@dataclass(frozen=True, slots=True)
class Trade:
    """An executed trade. The trades log is the authoritative record."""

    id: str
    ticker: str
    side: Side
    quantity: float
    price: float
    executed_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "executed_at": self.executed_at,
        }


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Total portfolio value at a point in time, for the P&L chart."""

    total_value: float
    recorded_at: str

    def to_dict(self) -> dict:
        return {"total_value": self.total_value, "recorded_at": self.recorded_at}


@dataclass(frozen=True, slots=True)
class PortfolioView:
    """The full portfolio response."""

    cash_balance: float
    positions: list[ValuedPosition]
    positions_value: float
    total_value: float
    unrealized_pnl: float

    def to_dict(self) -> dict:
        return {
            "cash_balance": self.cash_balance,
            "positions": [p.to_dict() for p in self.positions],
            "positions_value": self.positions_value,
            "total_value": self.total_value,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass(frozen=True, slots=True)
class TradeResult:
    """The outcome of a single executed trade."""

    trade: Trade
    cash_balance: float
    position: Position | None
    realized_pnl: float | None
    total_value: float

    def to_dict(self) -> dict:
        return {
            "trade": self.trade.to_dict(),
            "cash_balance": self.cash_balance,
            "position": self.position.to_dict() if self.position else None,
            "realized_pnl": self.realized_pnl,
            "total_value": self.total_value,
        }
