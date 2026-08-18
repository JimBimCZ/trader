"""Ticker canonicalization and validation.

Single source of truth for turning user-supplied, LLM-supplied, or seed ticker
strings into the canonical form used as a database key, cache key, and
simulator instrument key. Applied at every boundary — REST routes, the LLM
action executor, seed data, and inside both MarketDataSource implementations
as defence in depth.
"""

from __future__ import annotations

import re

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
    """True if the ticker is valid once canonicalized."""
    return bool(TICKER_PATTERN.match(canonicalize_ticker(ticker)))


def validate_ticker(ticker: str) -> str:
    """Canonicalize and validate, returning the canonical form.

    Raises ValueError if the ticker is not 1-5 letters. Callers at the API
    boundary translate this into an INVALID_TICKER error response.
    """
    canonical = canonicalize_ticker(ticker)
    if not TICKER_PATTERN.match(canonical):
        raise ValueError(f"Invalid ticker: {ticker!r}")
    return canonical
