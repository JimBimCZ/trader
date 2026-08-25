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


def _supplied_secret(request: Request) -> str:
    """The caller's proof of authorization, from whichever header carries it.

    Two callers use this route: a human or a non-Vercel scheduler, who sends
    `X-Cleanup-Secret` directly; and Vercel Cron, which cannot be configured
    to send a custom header at all -- its own mechanism is `Authorization:
    Bearer <CRON_SECRET>`, auto-attached whenever `CRON_SECRET` is set. Both
    are compared against the same configured secret (`Settings.cleanup_secret`,
    itself resolved from `CLEANUP_SECRET` or `CRON_SECRET`), so either header
    authorizes the same call.
    """
    direct = request.headers.get("X-Cleanup-Secret")
    if direct is not None:
        return direct
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :]
    return ""


@router.api_route("/admin/cleanup", methods=["GET", "POST"])
async def cleanup(request: Request) -> dict:
    """Expire idle guests. Driven by Vercel Cron, which issues a GET where no
    background task runs -- POST is also accepted for manual/curl use.

    Guarded by a shared secret rather than by user identity: there is no admin
    user in this app, and the endpoint must be callable by a scheduler.
    """
    secret = request.app.state.settings.cleanup_secret
    supplied = _supplied_secret(request)
    # Compared as bytes, not as str. Starlette decodes header bytes as
    # latin-1, so a single raw byte >= 0x80 in the header produces a str with
    # a codepoint above 127 -- and `compare_digest` refuses those with a
    # TypeError, turning an unauthenticated request into a 500 and a
    # traceback on the one route that deletes rows. Encoding first is total:
    # every str encodes to UTF-8, and the comparison stays constant-time.
    if not secret or not secrets.compare_digest(supplied.encode("utf-8"), secret.encode("utf-8")):
        raise CleanupForbiddenError(
            "Cleanup requires a valid X-Cleanup-Secret header, or an "
            "Authorization: Bearer header carrying the same secret."
        )
    deleted = await GuestCleaner(
        request.app.state.user_store, request.app.state.settings
    ).run_once()
    return {"deleted": deleted}
