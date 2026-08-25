"""Health, reset, and admin routes."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request

from ..deps import ResetServiceDep, TradeServiceDep
from ..errors import CleanupForbiddenError
from .cleanup import GuestCleaner
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


@router.api_route("/admin/cleanup", methods=["GET", "POST"])
async def cleanup(request: Request) -> dict:
    """Expire idle guests. Driven by Vercel Cron, which issues a GET where no
    background task runs -- POST is also accepted for manual/curl use.

    Guarded by a shared secret rather than by user identity: there is no admin
    user in this app, and the endpoint must be callable by a scheduler.
    """
    secret = request.app.state.settings.cleanup_secret
    supplied = request.headers.get("X-Cleanup-Secret", "")
    if not secret or not secrets.compare_digest(supplied, secret):
        raise CleanupForbiddenError("Cleanup requires a valid X-Cleanup-Secret header.")
    deleted = await GuestCleaner(
        request.app.state.user_store, request.app.state.settings
    ).run_once()
    return {"deleted": deleted}
