"""Tests for pure portfolio math."""

from __future__ import annotations

import pytest

from app.errors import ValuationUnavailableError
from app.portfolio.formulas import (
    buy_avg_cost,
    market_value,
    position_pct_change,
    realized_pnl,
    round_cash,
    round_quantity,
    total_value,
    unrealized_pnl,
    value_position,
)
from app.portfolio.models import Position


class TestRounding:
    def test_cash_is_two_decimal_places(self):
        """Money never carries sub-cent precision."""
        assert round_cash(10.005999) == 10.01

    def test_quantity_is_six_decimal_places(self):
        """Fractional shares are kept to 6dp."""
        assert round_quantity(1.23456789) == 1.234568


class TestMarketValue:
    def test_multiplies_quantity_by_price(self):
        assert market_value(10, 191.24) == 1912.40

    def test_zero_quantity_is_worth_nothing(self):
        assert market_value(0, 191.24) == 0.0


class TestUnrealizedPnl:
    def test_profit_when_price_exceeds_cost(self):
        assert unrealized_pnl(10, 190.0, 191.24) == 12.40

    def test_loss_when_price_is_below_cost(self):
        assert unrealized_pnl(10, 190.0, 185.0) == -50.0

    def test_flat_when_price_equals_cost(self):
        assert unrealized_pnl(10, 190.0, 190.0) == 0.0


class TestPositionPctChange:
    def test_measures_return_since_acquisition(self):
        """Return is from avg_cost, not from the session open."""
        assert position_pct_change(190.0, 199.5) == 5.0

    def test_negative_return(self):
        assert position_pct_change(200.0, 180.0) == -10.0

    def test_zero_cost_does_not_divide_by_zero(self):
        assert position_pct_change(0.0, 100.0) == 0.0


class TestBuyAvgCost:
    def test_first_purchase_sets_the_cost(self):
        assert buy_avg_cost(0, 0, 10, 190.0) == 190.0

    def test_weights_by_quantity(self):
        """Adding 10 at 200 to 10 held at 190 averages to 195."""
        assert buy_avg_cost(10, 190.0, 10, 200.0) == 195.0

    def test_unequal_quantities_weight_correctly(self):
        """A large add pulls the average toward the new price."""
        assert buy_avg_cost(1, 100.0, 9, 200.0) == 190.0


class TestRealizedPnl:
    def test_profit_on_a_sale_above_cost(self):
        assert realized_pnl(5, 190.0, 200.0) == 50.0

    def test_loss_on_a_sale_below_cost(self):
        assert realized_pnl(5, 190.0, 180.0) == -50.0


class TestValuePosition:
    def test_builds_every_derived_field(self):
        valued = value_position(Position("AAPL", 10, 190.0), 199.5)
        assert valued.market_value == 1995.0
        assert valued.unrealized_pnl == 95.0
        assert valued.pct_change == 5.0


class TestTotalValue:
    def test_cash_only_portfolio(self):
        assert total_value(10_000.0, [], {}) == 10_000.0

    def test_adds_position_values_to_cash(self):
        positions = [Position("AAPL", 10, 190.0), Position("MSFT", 2, 400.0)]
        prices = {"AAPL": 200.0, "MSFT": 410.0}
        assert total_value(1000.0, positions, prices) == 1000.0 + 2000.0 + 820.0

    def test_missing_price_raises_rather_than_valuing_at_zero(self):
        """A held ticker with no price is an error, never worth nothing.

        Valuing it at 0 would silently misreport the portfolio and write a
        plausible-looking wrong number into the P&L history.
        """
        with pytest.raises(ValuationUnavailableError) as exc_info:
            total_value(1000.0, [Position("AAPL", 10, 190.0)], {})
        assert exc_info.value.code == "VALUATION_UNAVAILABLE"
        assert "AAPL" in exc_info.value.message

    def test_missing_price_for_one_of_several_still_raises(self):
        positions = [Position("AAPL", 10, 190.0), Position("MSFT", 2, 400.0)]
        with pytest.raises(ValuationUnavailableError):
            total_value(1000.0, positions, {"AAPL": 200.0})
