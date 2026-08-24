"""Health and reset routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import CurrentUserDep, TradeServiceDep
from .service import health_status

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health(request: Request) -> dict:
    """Readiness detail: market source, tick recency, tracked tickers, DB."""
    state = request.app.state
    return await health_status(state.db, state.price_cache, state.source, state.settings)


@router.post("/reset")
async def reset(request: Request, service: TradeServiceDep, user: CurrentUserDep) -> dict:
    """Restore the seeded starting state and return the fresh portfolio."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    await request.app.state.reset_service.reset()
    view = await service.get_portfolio()
    return view.to_dict()
