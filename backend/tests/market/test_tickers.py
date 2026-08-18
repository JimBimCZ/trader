"""Tests for ticker canonicalization and validation."""

from __future__ import annotations

import pytest

from app.errors import InvalidTickerError
from app.market.tickers import (
    canonicalize_ticker,
    is_valid_ticker,
    validate_ticker,
)


class TestCanonicalizeTicker:
    def test_uppercases(self):
        """Lowercase input is uppercased."""
        assert canonicalize_ticker("aapl") == "AAPL"

    def test_strips_whitespace(self):
        """Surrounding whitespace is removed."""
        assert canonicalize_ticker("  MSFT \n") == "MSFT"

    def test_already_canonical_is_unchanged(self):
        """Canonical input passes through untouched."""
        assert canonicalize_ticker("NVDA") == "NVDA"

    def test_is_idempotent(self):
        """Canonicalizing twice equals canonicalizing once."""
        once = canonicalize_ticker(" tsla ")
        assert canonicalize_ticker(once) == once


class TestIsValidTicker:
    @pytest.mark.parametrize("ticker", ["A", "aapl", "GOOGL", " msft "])
    def test_accepts_one_to_five_letters(self, ticker):
        """One to five letters, in any case, with any padding, is valid."""
        assert is_valid_ticker(ticker) is True

    @pytest.mark.parametrize("ticker", ["", "   ", "TOOLONG", "BRK.B", "A1", "$AAPL", "123"])
    def test_rejects_everything_else(self, ticker):
        """Empty, overlong, and non-alphabetic symbols are rejected."""
        assert is_valid_ticker(ticker) is False


class TestValidateTicker:
    def test_returns_canonical_form(self):
        """A valid ticker is returned canonicalized."""
        assert validate_ticker(" nvda ") == "NVDA"

    def test_raises_the_typed_error_on_invalid(self):
        """An invalid ticker raises InvalidTickerError, not a bare ValueError.

        The typed error is what the handlers render as a 400 INVALID_TICKER;
        a ValueError would escape as a 500.
        """
        with pytest.raises(InvalidTickerError) as exc_info:
            validate_ticker("BRK.B")
        assert exc_info.value.code == "INVALID_TICKER"
        assert exc_info.value.status_code == 400
