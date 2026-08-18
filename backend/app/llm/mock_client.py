"""Deterministic chat client for tests, CI, and running without an API key.

The mapping below is the contract in API_CONTRACT §9. Backend and E2E both
build against it; if it changes, both change together.
"""

from __future__ import annotations

import re

from ..errors import LLMError
from .client import ChatClient
from .models import ChatCompletionSchema, TradeAction, WatchlistAction

TRADE_RE = re.compile(
    r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares\s+of\s+)?([A-Za-z]{1,5})\b", re.IGNORECASE
)
WATCHLIST_RE = re.compile(r"\b(add|remove)\s+([A-Za-z]{1,5})\b.*watchlist", re.IGNORECASE)
PORTFOLIO_RE = re.compile(r"\b(portfolio|position|holding)", re.IGNORECASE)

#: Sentinel that forces the failure path, so E2E can cover it.
ERROR_TRIGGER = "__mock_error__"


def _summarize(context: str) -> str:
    """Pull the headline figures out of the context block.

    Echoing the whole block would put internal prompt text in front of the
    user, so only the lines meant to be read are quoted.
    """
    wanted = ("Cash:", "Total value:", "Unrealized P&L:", "POSITIONS", "WATCHLIST", "- ")
    lines = [line for line in context.splitlines() if line.startswith(wanted)]
    return "\n".join(lines) if lines else "Your portfolio is ready."


class MockChatClient(ChatClient):
    """Keys off the user's message text. No network, fully reproducible."""

    async def complete(self, messages: list[dict]) -> ChatCompletionSchema:
        user_message = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        # The last system message is the portfolio context block; the first
        # is the system prompt, which must never be echoed to the user.
        context = next((m["content"] for m in reversed(messages) if m.get("role") == "system"), "")

        if ERROR_TRIGGER in user_message:
            raise LLMError("Mock failure triggered.")

        trade = TRADE_RE.search(user_message)
        if trade:
            side, quantity, ticker = (
                trade.group(1).lower(),
                float(trade.group(2)),
                trade.group(3).upper(),
            )
            verb = "Bought" if side == "buy" else "Sold"
            return ChatCompletionSchema(
                message=f"{verb} {quantity:g} {ticker} at the current market price.",
                trades=[TradeAction(ticker=ticker, side=side, quantity=quantity)],
            )

        watchlist = WATCHLIST_RE.search(user_message)
        if watchlist:
            action, ticker = watchlist.group(1).lower(), watchlist.group(2).upper()
            verb = "Added" if action == "add" else "Removed"
            preposition = "to" if action == "add" else "from"
            return ChatCompletionSchema(
                message=f"{verb} {ticker} {preposition} your watchlist.",
                watchlist_changes=[WatchlistAction(ticker=ticker, action=action)],
            )

        if PORTFOLIO_RE.search(user_message):
            summary = _summarize(context)
            return ChatCompletionSchema(
                message=(
                    f"{summary}\n\n"
                    "Concentration is the thing to watch: a single position above roughly "
                    "20% of total value is where one bad day starts to hurt."
                )
            )

        return ChatCompletionSchema(
            message=(
                "I can analyze your portfolio, suggest trades, execute them, and manage "
                'your watchlist. Try "how is my portfolio doing?" or "buy 10 AAPL".'
            )
        )
