"""Portfolio reads and trade execution."""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta

from ..db import Database
from ..errors import (
    InsufficientCashError,
    InsufficientSharesError,
    InvalidQuantityError,
    PriceUnavailableError,
)
from ..market import PriceCache
from ..market.tickers import validate_ticker
from ..reconcile import TickerReconciler
from .formulas import (
    buy_avg_cost,
    realized_pnl,
    round_cash,
    round_quantity,
    total_value,
    value_position,
)
from .models import EPSILON, PortfolioSnapshot, PortfolioView, Position, Side, TradeResult
from .repository import PositionRepository, SnapshotRepository, TradeRepository, UserRepository

logger = logging.getLogger(__name__)


class TradeService:
    """Executes trades and reports portfolio state.

    Every write holds `lock` for the whole transaction. aiosqlite serializes
    individual statements, but a trade is a read-validate-write sequence with
    await points in between; without the lock two concurrent trades could
    interleave and lose an update, and a second BEGIN IMMEDIATE on the shared
    connection would fail outright.
    """

    def __init__(
        self,
        db: Database,
        users: UserRepository,
        positions: PositionRepository,
        trades: TradeRepository,
        snapshots: SnapshotRepository,
        price_cache: PriceCache,
        reconciler: TickerReconciler,
        lock: asyncio.Lock,
    ) -> None:
        self._db = db
        self._users = users
        self._positions = positions
        self._trades = trades
        self._snapshots = snapshots
        self._prices = price_cache
        self._reconciler = reconciler
        self._lock = lock

    # --- Reads ---

    def _price_map(self) -> dict[str, float]:
        return {ticker: update.price for ticker, update in self._prices.get_all().items()}

    async def get_portfolio(self) -> PortfolioView:
        cash = round_cash(await self._users.get_cash())
        positions = await self._positions.list()
        prices = self._price_map()

        # Raises ValuationUnavailableError if a held ticker has no price.
        total = total_value(cash, positions, prices)

        valued = [value_position(p, prices[p.ticker]) for p in positions]
        positions_value = round_cash(sum(v.market_value for v in valued))
        pnl = round_cash(sum(v.unrealized_pnl for v in valued))

        return PortfolioView(
            cash_balance=cash,
            positions=valued,
            positions_value=positions_value,
            total_value=total,
            unrealized_pnl=pnl,
        )

    async def get_history(self, limit: int = 500) -> list[PortfolioSnapshot]:
        """Portfolio value snapshots, oldest first."""
        return await self._snapshots.list(limit=limit)

    async def current_total_value(self) -> float:
        cash = await self._users.get_cash()
        positions = await self._positions.list()
        return total_value(round_cash(cash), positions, self._price_map())

    # --- Writes ---

    async def execute_trade(self, raw_ticker: str, side: Side, raw_quantity: float) -> TradeResult:
        """Execute a market order at the current cached price.

        Validation order matches API_CONTRACT §3: ticker, quantity, price
        availability, then funds or shares.
        """
        ticker = validate_ticker(raw_ticker)

        if not math.isfinite(raw_quantity) or raw_quantity <= 0:
            raise InvalidQuantityError("Quantity must be a positive number.")
        quantity = round_quantity(raw_quantity)
        if quantity <= 0:
            raise InvalidQuantityError("Quantity is too small to trade.")

        # Trading an unwatched ticker starts tracking it (DECISIONS D-05).
        await self._reconciler.ensure_tracked(ticker)

        price = self._prices.get_price(ticker)
        if price is None:
            raise PriceUnavailableError(
                f"No price available for {ticker} yet. Try again in a moment."
            )

        async with self._lock:
            async with self._db.transaction():
                cash = round_cash(await self._users.get_cash())
                position = await self._positions.get(ticker)

                if side == "buy":
                    new_cash, new_position, realized = await self._apply_buy(
                        ticker, quantity, price, cash, position
                    )
                else:
                    new_cash, new_position, realized = await self._apply_sell(
                        ticker, quantity, price, cash, position
                    )

                await self._users.set_cash(new_cash)
                trade = await self._trades.insert(ticker, side, quantity, price)

                positions_after = await self._positions.list()
                total = total_value(new_cash, positions_after, self._price_map())
                await self._snapshots.insert(total)

        logger.info("Executed %s %s x%s @ %s", side, ticker, quantity, price)
        return TradeResult(
            trade=trade,
            cash_balance=new_cash,
            position=new_position,
            realized_pnl=realized,
            total_value=total,
        )

    async def _apply_buy(self, ticker, quantity, price, cash, position):
        cost = round_cash(quantity * price)
        if cost > cash + EPSILON:
            raise InsufficientCashError(
                f"Buying {quantity} {ticker} costs ${cost:,.2f} but only ${cash:,.2f} is available."
            )

        if position is None:
            new_qty, new_avg = quantity, round_cash(price)
        else:
            new_qty = round_quantity(position.quantity + quantity)
            new_avg = buy_avg_cost(position.quantity, position.avg_cost, quantity, price)

        await self._positions.upsert(ticker, new_qty, new_avg)
        return round_cash(cash - cost), Position(ticker, new_qty, new_avg), None

    async def _apply_sell(self, ticker, quantity, price, cash, position):
        held = position.quantity if position else 0.0
        if quantity > held + EPSILON:
            raise InsufficientSharesError(
                f"Cannot sell {quantity} {ticker}: only {held} held. Short selling is not allowed."
            )

        proceeds = round_cash(quantity * price)
        realized = realized_pnl(quantity, position.avg_cost, price)
        remaining = round_quantity(held - quantity)

        if remaining < EPSILON:
            # Delete rather than keeping a dust row behind.
            await self._positions.delete(ticker)
            new_position = None
        else:
            # avg_cost is unchanged by a sale; only the quantity moves.
            await self._positions.upsert(ticker, remaining, position.avg_cost)
            new_position = Position(ticker, remaining, position.avg_cost)

        return round_cash(cash + proceeds), new_position, realized

    async def write_snapshot(self) -> float | None:
        """Record the current total value. Returns it, or None if unvaluable."""
        try:
            total = await self.current_total_value()
        except Exception:
            logger.exception("Skipping snapshot: portfolio could not be valued")
            return None
        async with self._lock:
            async with self._db.transaction():
                await self._snapshots.insert(total)
        return total

    async def prune_snapshots(self, retention_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        async with self._lock:
            async with self._db.transaction():
                return await self._snapshots.prune_older_than(cutoff)
