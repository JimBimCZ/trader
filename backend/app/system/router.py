"""Health and reset routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..deps import ResetServiceDep, TradeServiceDep
from .service import health_status

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health(request: Request) -> dict:
    """Readiness detail: market source, tick recency, tracked tickers, DB."""
    state = request.app.state
    return await health_status(state.db, state.price_cache, state.source, state.settings)


@router.post("/reset")
async def reset(service: TradeServiceDep, reset_service: ResetServiceDep) -> dict:
    """Restore this user's seeded starting state and return their portfolio."""
    await reset_service.reset()
    view = await service.get_portfolio()
    return view.to_dict()
