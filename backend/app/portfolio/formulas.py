"""Pure portfolio math. No I/O, no database, no cache.

These are the single source of truth for every number the UI displays, so the
same rounding rules apply whether a value comes from a trade response, the
portfolio endpoint, or a snapshot.
"""

from __future__ import annotations

from ..errors import ValuationUnavailableError
from .models import EPSILON, Position, ValuedPosition


def round_cash(value: float) -> float:
    """Money is 2dp everywhere it is stored or returned."""
    return round(value, 2)


def round_quantity(value: float) -> float:
    """Share quantities are 6dp, which is well beyond any realistic fill."""
    return round(value, 6)


def market_value(quantity: float, price: float) -> float:
    """Current value of a holding."""
    return round_cash(quantity * price)


def unrealized_pnl(quantity: float, avg_cost: float, price: float) -> float:
    """Profit or loss on an open position, not yet realized by a sale."""
    return round_cash((price - avg_cost) * quantity)


def position_pct_change(avg_cost: float, price: float) -> float:
    """Return since acquisition, as a percentage.

    This is not the daily change: it is measured from avg_cost, not from the
    session open.
    """
    if avg_cost == 0:
        return 0.0
    return round((price - avg_cost) / avg_cost * 100, 4)


def buy_avg_cost(old_qty: float, old_avg: float, fill_qty: float, fill_price: float) -> float:
    """Weighted average cost after adding to a position."""
    total_qty = old_qty + fill_qty
    if total_qty <= EPSILON:
        return round_cash(fill_price)
    return round_cash((old_qty * old_avg + fill_qty * fill_price) / total_qty)


def realized_pnl(sell_qty: float, avg_cost: float, sell_price: float) -> float:
    """Profit or loss locked in by a sale. Computed on demand, never stored."""
    return round_cash((sell_price - avg_cost) * sell_qty)


def value_position(position: Position, price: float) -> ValuedPosition:
    """Price a position against the live cache."""
    return ValuedPosition(
        ticker=position.ticker,
        quantity=position.quantity,
        avg_cost=position.avg_cost,
        current_price=price,
        market_value=market_value(position.quantity, price),
        unrealized_pnl=unrealized_pnl(position.quantity, position.avg_cost, price),
        pct_change=position_pct_change(position.avg_cost, price),
    )


def total_value(cash: float, positions: list[Position], prices: dict[str, float]) -> float:
    """Cash plus the market value of every holding.

    Raises ValuationUnavailableError if any held ticker has no price. A
    missing price is never treated as zero: doing so would silently misreport
    the portfolio and corrupt the P&L history with a value that looks real.
    """
    total = cash
    for position in positions:
        price = prices.get(position.ticker)
        if price is None:
            raise ValuationUnavailableError(
                f"No current price for {position.ticker}; portfolio cannot be valued."
            )
        total += position.quantity * price
    return round_cash(total)
