"""Data models for market data."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of a single ticker's price at a point in time."""

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)  # Unix seconds
    session_open: float = 0.0  # Session baseline: seed price (sim) or prev close (Massive)

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def daily_change(self) -> float:
        """Absolute change from the session baseline, not from the previous tick."""
        if not self.session_open:
            return 0.0
        return round(self.price - self.session_open, 4)

    @property
    def daily_change_percent(self) -> float:
        """Percentage change from the session baseline.

        This is the number the UI labels "daily change %". Do not confuse it
        with change_percent, which is tick-over-tick and near zero.
        """
        if not self.session_open:
            return 0.0
        return round((self.price - self.session_open) / self.session_open * 100, 4)

    @property
    def direction(self) -> str:
        if self.price > self.previous_price:
            return "up"
        elif self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "session_open": self.session_open,
            "change": self.change,
            "change_percent": self.change_percent,
            "daily_change": self.daily_change,
            "daily_change_percent": self.daily_change_percent,
            "direction": self.direction,
        }
