"""Ticker canonicalization and validation.

Single source of truth for turning user-supplied, LLM-supplied, or seed ticker
strings into the canonical form used as a database key, cache key, and
simulator instrument key. Applied at every boundary — REST routes, the LLM
action executor, seed data, and inside both MarketDataSource implementations
as defence in depth.
"""

from __future__ import annotations

import re

from ..errors import InvalidTickerError

#: A ticker is 1-5 ASCII letters once canonicalized. Deliberately strict:
#: it rejects hallucinated symbols, empty strings, and injection attempts
#: before they ever reach the database or an external API.
TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


def canonicalize_ticker(ticker: str) -> str:
    """Return the canonical form of a ticker: trimmed and uppercased.

    Does not validate. Use is_valid_ticker() or validate_ticker() for that.
    """
    return ticker.strip().upper()


def is_valid_ticker(ticker: str) -> bool:
    return bool(TICKER_PATTERN.match(canonicalize_ticker(ticker)))


def validate_ticker(ticker: str) -> str:
    """Canonicalize and validate, returning the canonical form.

    Raises InvalidTickerError, which the error handlers render as a 400 with
    code INVALID_TICKER. Raising the typed error here rather than a bare
    ValueError means no call site can forget to translate it.
    """
    canonical = canonicalize_ticker(ticker)
    if not TICKER_PATTERN.match(canonical):
        raise InvalidTickerError(
            f"'{ticker.strip()}' is not a valid ticker. Use 1-5 letters, e.g. AAPL."
        )
    return canonical
