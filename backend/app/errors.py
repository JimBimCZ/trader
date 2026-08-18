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


def _envelope(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"code": code, "message": message}}
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install the three handlers that produce the error envelope."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in detail.get("loc", ())[1:]) or "request"
        return _envelope("VALIDATION_ERROR", f"Invalid value for {field}.", 422)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the real cause; never leak internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _envelope("INTERNAL_ERROR", "An unexpected error occurred.", 500)


class FrontendNotBuiltError(AppError):
    """The static export is missing from the image or working tree.

    A deployment problem rather than a client one, so it is reported as 503
    instead of a 404 that would look like a bad URL.
    """

    status_code, code = 503, "FRONTEND_NOT_BUILT"
