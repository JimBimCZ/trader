"""Watchlist HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..deps import WatchlistServiceDep

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


@router.get("")
async def list_watchlist(service: WatchlistServiceDep) -> dict:
    """Watched tickers, oldest first. Prices come from SSE, not from here."""
    return {"tickers": await service.list(), "cap": service.cap}


@router.post("")
async def add_ticker(body: AddTickerRequest, service: WatchlistServiceDep) -> dict:
    """Add a ticker. Idempotent."""
    return {"tickers": await service.add(body.ticker), "cap": service.cap}


@router.delete("/{ticker}")
async def remove_ticker(ticker: str, service: WatchlistServiceDep) -> dict:
    """Remove a ticker. Allowed even while the position is still held."""
    return {"tickers": await service.remove(ticker), "cap": service.cap}
