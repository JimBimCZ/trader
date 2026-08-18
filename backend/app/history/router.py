"""Price history HTTP route."""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import HistoryStoreDep
from ..errors import TickerNotFoundError
from ..market.tickers import validate_ticker

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/{ticker}")
async def get_history(ticker: str, store: HistoryStoreDep) -> dict:
    """Recent price points for a ticker, oldest first.

    Seeds charts on first paint. Timestamps are Unix float seconds, matching
    the SSE payload rather than the ISO strings used elsewhere.
    """
    canonical = validate_ticker(ticker)
    points = store.get(canonical)
    if points is None:
        raise TickerNotFoundError(f"{canonical} is not being tracked.")
    return {
        "ticker": canonical,
        "points": [{"timestamp": ts, "price": price} for ts, price in points],
    }
