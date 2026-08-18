"""In-memory price history, so charts have shape on first paint.

Without this, every chart is empty for the first seconds after a reload while
the SSE stream accumulates points. The buffer is deliberately in memory only:
it is a display convenience, not a record, and it is cheap to rebuild.
"""

from __future__ import annotations

from collections import deque


class HistoryStore:
    """A bounded ring buffer of (timestamp, price) points per ticker.

    Touched only from the event loop — the collector task and the route
    handler — so unlike PriceCache it needs no lock.
    """

    def __init__(self, maxlen: int = 600) -> None:
        self._maxlen = maxlen
        self._points: dict[str, deque[tuple[float, float]]] = {}

    def append(self, ticker: str, timestamp: float, price: float) -> None:
        """Record a point, evicting the oldest once the buffer is full."""
        buffer = self._points.get(ticker)
        if buffer is None:
            buffer = deque(maxlen=self._maxlen)
            self._points[ticker] = buffer
        # Skip duplicate timestamps: the collector polls faster than some
        # sources tick, and repeating a point would flat-line the chart.
        if buffer and buffer[-1][0] == timestamp:
            return
        buffer.append((timestamp, price))

    def get(self, ticker: str) -> list[tuple[float, float]] | None:
        """Points for a ticker oldest-first, or None if never tracked."""
        buffer = self._points.get(ticker)
        return list(buffer) if buffer is not None else None

    def track(self, ticker: str) -> None:
        """Register a ticker so it reports empty rather than unknown."""
        self._points.setdefault(ticker, deque(maxlen=self._maxlen))

    def drop(self, ticker: str) -> None:
        self._points.pop(ticker, None)

    def clear(self) -> None:
        """Forget everything. Used by POST /api/reset."""
        self._points.clear()

    def __len__(self) -> int:
        return len(self._points)

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._points
