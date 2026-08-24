"""Price history computed backwards from now, for the deterministic source.

`HistoryStore` exists because charts are empty on first paint while the SSE
stream accumulates points, and it fills by having a background task copy every
tick into a ring buffer. With prices a function of time the buffer is redundant:
the last N ticks can simply be evaluated, which also means the history survives
a cold start instead of restarting empty.
"""

from __future__ import annotations

from ..market.deterministic_source import DeterministicPriceCache
from ..market.tickers import canonicalize_ticker
from .buffer import HistoryStore


class DeterministicHistoryStore(HistoryStore):
    """A `HistoryStore` that evaluates the recent past rather than recording it."""

    def __init__(self, price_cache: DeterministicPriceCache, maxlen: int = 600) -> None:
        super().__init__(maxlen=maxlen)
        self._cache = price_cache
        self._maxlen = maxlen

    def append(self, ticker: str, timestamp: float, price: float) -> None:
        """No-op: nothing accumulates, so there is nothing to record."""

    def get(self, ticker: str) -> list[tuple[float, float]] | None:
        canonical = canonicalize_ticker(ticker)
        if canonical not in self._cache:
            return None

        latest = self._cache.current_tick()
        # A tick index below zero would be a timestamp before 1970; the walk is
        # defined there, but reporting it would be nonsense.
        first = max(0, latest - self._maxlen + 1)
        return [
            (self._cache.tick_time(tick), self._cache.build_update(canonical, tick).price)
            for tick in range(first, latest + 1)
        ]

    def track(self, ticker: str) -> None:
        """Tracking is the cache's concern; a tracked ticker already has history."""

    def drop(self, ticker: str) -> None:
        """Dropping is the cache's concern."""

    def clear(self) -> None:
        """Nothing is stored, so a reset has nothing to clear."""

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, ticker: str) -> bool:
        return canonicalize_ticker(ticker) in self._cache
