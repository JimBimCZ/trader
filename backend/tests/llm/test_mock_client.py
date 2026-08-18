"""Tests for the deterministic mock chat client.

This is the contract in API_CONTRACT §9; the E2E suite depends on it behaving
exactly as specified.
"""

from __future__ import annotations

import pytest

from app.errors import LLMError
from app.llm.mock_client import MockChatClient


def messages(text: str) -> list[dict]:
    return [{"role": "system", "content": "CONTEXT"}, {"role": "user", "content": text}]


class TestTradeIntent:
    @pytest.mark.parametrize(
        ("text", "side", "quantity", "ticker"),
        [
            ("buy 10 AAPL", "buy", 10.0, "AAPL"),
            ("sell 5 MSFT", "sell", 5.0, "MSFT"),
            ("buy 10 shares of aapl", "buy", 10.0, "AAPL"),
            ("Please BUY 2.5 NVDA now", "buy", 2.5, "NVDA"),
        ],
    )
    async def test_extracts_the_trade(self, text, side, quantity, ticker):
        """Each documented phrasing produces exactly one matching trade."""
        response = await MockChatClient().complete(messages(text))
        assert len(response.trades) == 1
        assert response.trades[0].side == side
        assert response.trades[0].quantity == quantity
        assert response.trades[0].ticker == ticker

    async def test_mentions_the_trade_in_the_message(self):
        response = await MockChatClient().complete(messages("buy 10 AAPL"))
        assert "AAPL" in response.message


class TestWatchlistIntent:
    @pytest.mark.parametrize(
        ("text", "action", "ticker"),
        [
            ("add PYPL to my watchlist", "add", "PYPL"),
            ("remove tsla from the watchlist", "remove", "TSLA"),
        ],
    )
    async def test_extracts_the_change(self, text, action, ticker):
        response = await MockChatClient().complete(messages(text))
        assert len(response.watchlist_changes) == 1
        assert response.watchlist_changes[0].action == action
        assert response.watchlist_changes[0].ticker == ticker

    async def test_does_not_also_emit_a_trade(self):
        response = await MockChatClient().complete(messages("add PYPL to my watchlist"))
        assert response.trades == []


class TestPortfolioIntent:
    @pytest.mark.parametrize("text", ["how is my portfolio?", "show positions", "my holdings"])
    async def test_returns_analysis_without_actions(self, text):
        response = await MockChatClient().complete(messages(text))
        assert response.trades == []
        assert response.watchlist_changes == []
        assert response.message

    async def test_quotes_the_supplied_context(self):
        """The analysis reflects real portfolio numbers, not invented ones."""
        msgs = [
            {"role": "system", "content": "Cash: $1,234.56"},
            {"role": "user", "content": "how is my portfolio?"},
        ]
        response = await MockChatClient().complete(msgs)
        assert "1,234.56" in response.message


class TestFallback:
    async def test_unmatched_input_returns_a_canned_reply(self):
        response = await MockChatClient().complete(messages("hello there"))
        assert response.message
        assert response.trades == []
        assert response.watchlist_changes == []


class TestErrorTrigger:
    async def test_the_sentinel_raises(self):
        """A sentinel drives the failure path so E2E can cover it."""
        with pytest.raises(LLMError):
            await MockChatClient().complete(messages("__mock_error__"))


class TestDeterminism:
    async def test_the_same_input_always_produces_the_same_output(self):
        client = MockChatClient()
        first = await client.complete(messages("buy 10 AAPL"))
        second = await client.complete(messages("buy 10 AAPL"))
        assert first.model_dump() == second.model_dump()
