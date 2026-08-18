"""Tests for trade execution and portfolio reporting."""

from __future__ import annotations

import asyncio

import pytest

from app.errors import (
    InsufficientCashError,
    InsufficientSharesError,
    InvalidQuantityError,
    InvalidTickerError,
    PriceUnavailableError,
)


class TestBuy:
    async def test_buy_reduces_cash_and_opens_a_position(self, services):
        """A buy debits cash and creates the position at the fill price."""
        await services.track("AAPL", price=190.0)
        result = await services.trade_service.execute_trade("AAPL", "buy", 10)

        assert result.trade.price == 190.0
        assert result.cash_balance == 8100.0
        assert result.position.quantity == 10
        assert result.position.avg_cost == 190.0
        assert result.realized_pnl is None

    async def test_second_buy_averages_the_cost(self, services):
        """Adding to a position produces a quantity-weighted average cost."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)
        services.price_cache.update("AAPL", 200.0)
        result = await services.trade_service.execute_trade("AAPL", "buy", 10)

        assert result.position.quantity == 20
        assert result.position.avg_cost == 195.0

    async def test_lowercase_ticker_is_canonicalized(self, services):
        """A lowercase ticker trades the canonical instrument."""
        await services.track("AAPL", price=190.0)
        result = await services.trade_service.execute_trade("  aapl ", "buy", 1)
        assert result.trade.ticker == "AAPL"

    async def test_fractional_quantities_are_supported(self, services):
        await services.track("AAPL", price=190.0)
        result = await services.trade_service.execute_trade("AAPL", "buy", 0.5)
        assert result.position.quantity == 0.5

    async def test_insufficient_cash_is_rejected(self, services):
        """A buy beyond the balance fails with a machine-readable code."""
        await services.track("AAPL", price=190.0)
        with pytest.raises(InsufficientCashError) as exc_info:
            await services.trade_service.execute_trade("AAPL", "buy", 1000)
        assert exc_info.value.code == "INSUFFICIENT_CASH"

    async def test_a_rejected_buy_changes_nothing(self, services):
        """Failed validation leaves cash and positions untouched."""
        await services.track("AAPL", price=190.0)
        with pytest.raises(InsufficientCashError):
            await services.trade_service.execute_trade("AAPL", "buy", 1000)

        assert await services.users.get_cash() == 10_000.0
        assert await services.positions.list() == []

    async def test_buying_the_exact_cash_balance_succeeds(self, services):
        """Spending everything is allowed; the epsilon guard permits equality."""
        await services.track("AAPL", price=100.0)
        result = await services.trade_service.execute_trade("AAPL", "buy", 100)
        assert result.cash_balance == 0.0


class TestSell:
    async def test_sell_credits_cash_and_reduces_the_position(self, services):
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)
        services.price_cache.update("AAPL", 200.0)
        result = await services.trade_service.execute_trade("AAPL", "sell", 4)

        assert result.position.quantity == 6
        assert result.cash_balance == 8100.0 + 800.0
        assert result.realized_pnl == 40.0

    async def test_avg_cost_is_unchanged_by_a_sale(self, services):
        """Selling never moves the cost basis of what remains."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)
        services.price_cache.update("AAPL", 250.0)
        result = await services.trade_service.execute_trade("AAPL", "sell", 5)
        assert result.position.avg_cost == 190.0

    async def test_full_sell_deletes_the_position(self, services):
        """A complete liquidation removes the row rather than leaving zero."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)
        result = await services.trade_service.execute_trade("AAPL", "sell", 10)

        assert result.position is None
        assert await services.positions.get("AAPL") is None

    async def test_full_sell_of_a_fractional_position_leaves_no_dust(self, services):
        """Float arithmetic must not leave a 1e-14 position behind."""
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 0.1)
        await services.trade_service.execute_trade("AAPL", "buy", 0.2)
        await services.trade_service.execute_trade("AAPL", "sell", 0.3)
        assert await services.positions.get("AAPL") is None

    async def test_selling_more_than_held_is_rejected(self, services):
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 5)
        with pytest.raises(InsufficientSharesError):
            await services.trade_service.execute_trade("AAPL", "sell", 6)

    async def test_short_selling_is_not_allowed(self, services):
        """Selling with no position at all is refused."""
        await services.track("AAPL", price=190.0)
        with pytest.raises(InsufficientSharesError) as exc_info:
            await services.trade_service.execute_trade("AAPL", "sell", 1)
        assert "Short selling" in exc_info.value.message

    async def test_selling_at_a_loss_records_negative_realized_pnl(self, services):
        await services.track("AAPL", price=200.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)
        services.price_cache.update("AAPL", 150.0)
        result = await services.trade_service.execute_trade("AAPL", "sell", 10)
        assert result.realized_pnl == -500.0


class TestValidation:
    async def test_invalid_ticker_is_rejected(self, services):
        with pytest.raises(InvalidTickerError):
            await services.trade_service.execute_trade("BRK.B", "buy", 1)

    @pytest.mark.parametrize("quantity", [0, -5, float("inf"), float("nan")])
    async def test_non_positive_or_infinite_quantity_is_rejected(self, services, quantity):
        await services.track("AAPL", price=190.0)
        with pytest.raises(InvalidQuantityError):
            await services.trade_service.execute_trade("AAPL", "buy", quantity)

    async def test_quantity_below_rounding_precision_is_rejected(self, services):
        """A quantity that rounds to zero cannot be traded."""
        await services.track("AAPL", price=190.0)
        with pytest.raises(InvalidQuantityError):
            await services.trade_service.execute_trade("AAPL", "buy", 1e-9)

    async def test_missing_price_refuses_rather_than_filling_at_zero(self, services):
        """An untracked ticker with no price is a 409, not a free fill."""
        with pytest.raises(PriceUnavailableError) as exc_info:
            await services.trade_service.execute_trade("ZZZ", "buy", 1)
        assert exc_info.value.status_code == 409


class TestAutoTracking:
    async def test_trading_an_unwatched_ticker_starts_tracking_it(self, services):
        """A trade on an unwatched ticker adds it to the price source."""
        services.price_cache.update("PYPL", 60.0, session_open=60.0)
        await services.trade_service.execute_trade("PYPL", "buy", 1)
        assert "PYPL" in services.source.get_tickers()


class TestPortfolioView:
    async def test_empty_portfolio_is_all_cash(self, services):
        view = await services.trade_service.get_portfolio()
        assert view.cash_balance == 10_000.0
        assert view.total_value == 10_000.0
        assert view.positions == []

    async def test_positions_are_priced_live(self, services):
        await services.track("AAPL", price=190.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)
        services.price_cache.update("AAPL", 200.0)

        view = await services.trade_service.get_portfolio()
        assert view.positions[0].current_price == 200.0
        assert view.positions[0].unrealized_pnl == 100.0
        assert view.total_value == 8100.0 + 2000.0
        assert view.unrealized_pnl == 100.0


class TestSnapshots:
    async def test_a_trade_writes_a_snapshot_immediately(self, services):
        """The P&L chart reacts to a trade without waiting for the timer."""
        await services.track("AAPL", price=190.0)
        before = len(await services.trade_service.get_history())
        await services.trade_service.execute_trade("AAPL", "buy", 1)
        assert len(await services.trade_service.get_history()) == before + 1

    async def test_history_is_returned_oldest_first(self, services):
        await services.track("AAPL", price=190.0)
        for _ in range(3):
            await services.trade_service.execute_trade("AAPL", "buy", 1)
        history = await services.trade_service.get_history()
        assert history == sorted(history, key=lambda s: s.recorded_at)

    async def test_history_respects_the_limit(self, services):
        await services.track("AAPL", price=190.0)
        for _ in range(5):
            await services.trade_service.execute_trade("AAPL", "buy", 1)
        assert len(await services.trade_service.get_history(limit=2)) == 2


class TestConcurrency:
    async def test_concurrent_buys_do_not_lose_an_update(self, services):
        """Ten parallel trades must all be reflected in cash and quantity.

        Without the service lock these interleave on the shared connection and
        the last writer wins, silently giving away shares.
        """
        await services.track("AAPL", price=100.0)
        await asyncio.gather(
            *(services.trade_service.execute_trade("AAPL", "buy", 1) for _ in range(10))
        )

        position = await services.positions.get("AAPL")
        assert position.quantity == 10
        assert await services.users.get_cash() == 9000.0

    async def test_concurrent_oversell_attempts_cannot_go_negative(self, services):
        """Parallel sells of the whole position cannot both succeed."""
        await services.track("AAPL", price=100.0)
        await services.trade_service.execute_trade("AAPL", "buy", 10)

        results = await asyncio.gather(
            *(services.trade_service.execute_trade("AAPL", "sell", 10) for _ in range(3)),
            return_exceptions=True,
        )
        successes = [r for r in results if not isinstance(r, Exception)]
        assert len(successes) == 1
        assert await services.positions.get("AAPL") is None
