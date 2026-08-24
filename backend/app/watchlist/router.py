"""Watchlist HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..deps import CurrentUserDep, WatchlistServiceDep

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


@router.get("")
async def list_watchlist(service: WatchlistServiceDep, user: CurrentUserDep) -> dict:
    """Watched tickers, oldest first. Prices come from SSE, not from here."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    return {"tickers": await service.list(), "cap": service.cap}


@router.post("")
async def add_ticker(
    body: AddTickerRequest, service: WatchlistServiceDep, user: CurrentUserDep
) -> dict:
    """Add a ticker. Idempotent."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    return {"tickers": await service.add(body.ticker), "cap": service.cap}


@router.delete("/{ticker}")
async def remove_ticker(ticker: str, service: WatchlistServiceDep, user: CurrentUserDep) -> dict:
    """Remove a ticker. Allowed even while the position is still held."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    return {"tickers": await service.remove(ticker), "cap": service.cap}
