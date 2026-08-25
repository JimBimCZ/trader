"""Application error hierarchy and the single JSON error envelope.

Every route raises an AppError subclass; the handlers registered here turn it
into {"error": {"code", "message"}}. No route builds an error body by hand.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, client-facing failures."""

    status_code: int = 400
    code: str = "ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidTickerError(AppError):
    status_code, code = 400, "INVALID_TICKER"


class InvalidQuantityError(AppError):
    status_code, code = 400, "INVALID_QUANTITY"


class InsufficientCashError(AppError):
    status_code, code = 400, "INSUFFICIENT_CASH"


class InsufficientSharesError(AppError):
    status_code, code = 400, "INSUFFICIENT_SHARES"


class WatchlistFullError(AppError):
    status_code, code = 400, "WATCHLIST_FULL"


class MarketCapacityFullError(AppError):
    """The global tracked-ticker set is full.

    Deliberately distinct from WATCHLIST_FULL: this is a limit on what the
    whole deployment polls, not on the caller's own list. Reporting it as
    WATCHLIST_FULL would tell a user their watchlist is full when it holds
    three tickers.
    """

    status_code, code = 503, "MARKET_CAPACITY_FULL"


class TickerNotFoundError(AppError):
    status_code, code = 404, "TICKER_NOT_FOUND"


class PriceUnavailableError(AppError):
    """No cached price at trade time. The trade is refused, never filled at 0."""

    status_code, code = 409, "PRICE_UNAVAILABLE"


class ValuationUnavailableError(AppError):
    """A held position has no cached price, so the portfolio cannot be valued.

    Deliberately an error rather than valuing the position at 0, which would
    silently tank the P&L chart and the heatmap with no visible cause.
    """

    status_code, code = 500, "VALUATION_UNAVAILABLE"


class LLMError(AppError):
    """Upstream model failure.

    Never reaches the client as an error response: ChatService catches it and
    returns HTTP 200 with error=true, per API_CONTRACT §7. The status code
    exists so internal callers and tests see a sensible value.
    """

    status_code, code = 502, "LLM_ERROR"


#: Where `deps._set_session_cookie` parks the rendered `Set-Cookie` value, on
#: `request.state`, so the handlers below can put it back on their own
#: response. The name lives here rather than in `deps` because `deps` imports
#: this module and not the other way round.
PENDING_SESSION_COOKIE_ATTR = "pending_session_cookie"


def _envelope(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    """The error body, carrying whatever session the request already resolved.

    The handlers run after the dependency that mints and signs a guest, and
    they build a fresh response rather than reusing the dependency's
    sub-response -- so the `Set-Cookie` that dependency wrote is dropped
    unless it is copied across here. Dropped, a first request that failed
    created a user the browser was never told about, and the retry created
    another.
    """
    response = JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )
    pending = getattr(request.state, PENDING_SESSION_COOKIE_ATTR, None)
    if pending:
        response.headers.append("set-cookie", pending)
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """Install the three handlers that produce the error envelope."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(request, exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in detail.get("loc", ())[1:]) or "request"
        return _envelope(request, "VALIDATION_ERROR", f"Invalid value for {field}.", 422)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the real cause; never leak internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _envelope(request, "INTERNAL_ERROR", "An unexpected error occurred.", 500)


class FrontendNotBuiltError(AppError):
    """The static export is missing from the image or working tree.

    A deployment problem rather than a client one, so it is reported as 503
    instead of a 404 that would look like a bad URL.
    """

    status_code, code = 503, "FRONTEND_NOT_BUILT"


class RouteNotFoundError(AppError):
    """An /api path that no router claims.

    The SPA fallback matches every path, so without this an unknown API URL
    would be answered with the app shell — or, where the frontend is served by
    a CDN rather than by this process, with FRONTEND_NOT_BUILT.
    """

    status_code, code = 404, "ROUTE_NOT_FOUND"


class ConfigurationError(AppError):
    """The process cannot start with the configuration it was given."""

    status_code, code = 500, "CONFIGURATION_ERROR"


class CleanupForbiddenError(AppError):
    """The guest-cleanup route was called without a valid secret, in either
    the `X-Cleanup-Secret` header or an `Authorization: Bearer` header.

    Also what an unset `cleanup_secret` produces on every call -- the safe
    default for an endpoint that deletes rows.
    """

    status_code, code = 403, "CLEANUP_FORBIDDEN"


class AuthProviderUnavailableError(AppError):
    """A provider that is not configured on this deployment.

    404 rather than 400: the route genuinely does not exist here, and saying
    so lets the frontend hide a button it cannot fulfil rather than render one
    that dead-ends.
    """

    status_code, code = 404, "AUTH_PROVIDER_UNAVAILABLE"


class AuthStateInvalidError(AppError):
    """The callback's state or PKCE verifier did not match the cookie.

    Ordinary rather than sinister: a bookmarked callback URL, a back button,
    or a sign-in begun before a redeploy rotated the secret all land here.
    """

    status_code, code = 400, "AUTH_STATE_INVALID"


class AuthExchangeFailedError(AppError):
    """The provider refused the code exchange or the userinfo request."""

    status_code, code = 502, "AUTH_EXCHANGE_FAILED"


class ClaimTokenInvalidError(AppError):
    """A claim token that is expired, tampered with, or not this session's."""

    status_code, code = 400, "CLAIM_TOKEN_INVALID"
