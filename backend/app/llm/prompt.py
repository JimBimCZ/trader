"""System prompt and context construction for the chat assistant."""

from __future__ import annotations

from ..portfolio.models import PortfolioView
from .models import ChatMessage

SYSTEM_PROMPT = """You are trader, an AI trading assistant embedded in a simulated \
trading terminal. The portfolio is virtual money — no real funds are at risk.

Your job:
- Analyze portfolio composition, concentration risk, and P&L.
- Suggest trades with brief, concrete reasoning.
- Execute trades when the user asks for them or agrees to your suggestion.
- Manage the watchlist when it helps.

Rules:
- Be concise and data-driven. No hedging, no filler, no disclaimers about being an AI.
- Quote real numbers from the portfolio context rather than inventing them.
- Only put a trade in `trades` when the user actually wants it executed. Discussing an \
idea is not an instruction to trade.
- Tickers are 1-5 letters, uppercase.
- Selling more than is held, or buying beyond available cash, will be rejected — check \
the context before proposing either.
- Always respond with valid JSON matching the required schema."""


def build_context_block(portfolio: PortfolioView, watchlist: list[str]) -> str:
    """Render the live portfolio state the model reasons over."""
    lines = [
        "CURRENT PORTFOLIO",
        f"Cash: ${portfolio.cash_balance:,.2f}",
        f"Total value: ${portfolio.total_value:,.2f}",
        f"Unrealized P&L: ${portfolio.unrealized_pnl:,.2f}",
        "",
    ]

    if portfolio.positions:
        lines.append("POSITIONS")
        for p in portfolio.positions:
            weight = (p.market_value / portfolio.total_value * 100) if portfolio.total_value else 0
            lines.append(
                f"- {p.ticker}: {p.quantity:g} shares @ avg ${p.avg_cost:,.2f}, "
                f"now ${p.current_price:,.2f}, value ${p.market_value:,.2f} "
                f"({weight:.1f}% of portfolio), P&L ${p.unrealized_pnl:,.2f} "
                f"({p.pct_change:+.2f}%)"
            )
    else:
        lines.append("POSITIONS: none — the portfolio is all cash.")

    lines.extend(["", f"WATCHLIST: {', '.join(watchlist) if watchlist else 'empty'}"])
    return "\n".join(lines)


def build_messages(
    context_block: str,
    history: list[ChatMessage],
    user_message: str,
    char_budget: int = 8000,
) -> list[dict]:
    """Assemble the message list sent to the model.

    History is trimmed newest-first against a character budget, so a long
    conversation bounds both cost and latency.
    """
    trimmed: list[ChatMessage] = []
    used = 0
    for message in reversed(history):
        used += len(message.content)
        if used > char_budget:
            break
        trimmed.append(message)
    trimmed.reverse()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_block},
    ]
    messages.extend({"role": m.role, "content": m.content} for m in trimmed)
    messages.append({"role": "user", "content": user_message})
    return messages
