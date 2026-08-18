"""Tests for PriceUpdate dataclass."""

import pytest

from app.market.models import PriceUpdate


class TestPriceUpdate:
    """Unit tests for the PriceUpdate model."""

    def test_price_update_creation(self):
        """Test basic PriceUpdate creation."""
        update = PriceUpdate(
            ticker="AAPL", price=190.50, previous_price=190.00, timestamp=1234567890.0
        )
        assert update.ticker == "AAPL"
        assert update.price == 190.50
        assert update.previous_price == 190.00
        assert update.timestamp == 1234567890.0

    def test_change_calculation(self):
        """Test price change calculation."""
        update = PriceUpdate(
            ticker="AAPL", price=190.50, previous_price=190.00, timestamp=1234567890.0
        )
        assert update.change == 0.50

    def test_change_negative(self):
        """Test negative price change."""
        update = PriceUpdate(
            ticker="AAPL", price=189.50, previous_price=190.00, timestamp=1234567890.0
        )
        assert update.change == -0.50

    def test_change_percent_up(self):
        """Test percentage change calculation (up)."""
        update = PriceUpdate(
            ticker="AAPL", price=190.00, previous_price=100.00, timestamp=1234567890.0
        )
        assert update.change_percent == 90.0

    def test_change_percent_down(self):
        """Test percentage change calculation (down)."""
        update = PriceUpdate(
            ticker="AAPL", price=100.00, previous_price=200.00, timestamp=1234567890.0
        )
        assert update.change_percent == -50.0

    def test_change_percent_zero_previous(self):
        """Test percentage change with zero previous price."""
        update = PriceUpdate(
            ticker="AAPL", price=100.00, previous_price=0.00, timestamp=1234567890.0
        )
        assert update.change_percent == 0.0

    def test_direction_up(self):
        """Test direction calculation (up)."""
        update = PriceUpdate(
            ticker="AAPL", price=191.00, previous_price=190.00, timestamp=1234567890.0
        )
        assert update.direction == "up"

    def test_direction_down(self):
        """Test direction calculation (down)."""
        update = PriceUpdate(
            ticker="AAPL", price=189.00, previous_price=190.00, timestamp=1234567890.0
        )
        assert update.direction == "down"

    def test_direction_flat(self):
        """Test direction calculation (flat)."""
        update = PriceUpdate(
            ticker="AAPL", price=190.00, previous_price=190.00, timestamp=1234567890.0
        )
        assert update.direction == "flat"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        update = PriceUpdate(
            ticker="AAPL", price=190.50, previous_price=190.00, timestamp=1234567890.0
        )
        result = update.to_dict()

        assert result["ticker"] == "AAPL"
        assert result["price"] == 190.50
        assert result["previous_price"] == 190.00
        assert result["timestamp"] == 1234567890.0
        assert result["change"] == 0.50
        assert result["change_percent"] == 0.2632  # (0.50 / 190.00) * 100
        assert result["direction"] == "up"

    def test_immutability(self):
        """Test that PriceUpdate is immutable."""
        update = PriceUpdate(
            ticker="AAPL", price=190.50, previous_price=190.00, timestamp=1234567890.0
        )

        with pytest.raises(AttributeError):
            update.price = 200.00  # Should raise error


class TestSessionOpen:
    """Daily change is measured from session_open, not from the previous tick."""

    def test_defaults_to_zero(self):
        """session_open defaults to 0.0 when not supplied."""
        update = PriceUpdate(ticker="AAPL", price=190.0, previous_price=189.0)
        assert update.session_open == 0.0

    def test_daily_change_is_zero_without_a_baseline(self):
        """With no session_open, daily change degrades to 0 rather than dividing by zero."""
        update = PriceUpdate(ticker="AAPL", price=190.0, previous_price=189.0)
        assert update.daily_change == 0.0
        assert update.daily_change_percent == 0.0

    def test_daily_change_measures_from_session_open(self):
        """Daily change uses the session baseline, not the previous tick."""
        update = PriceUpdate(ticker="AAPL", price=199.5, previous_price=199.4, session_open=190.0)
        assert update.daily_change == 9.5
        assert update.daily_change_percent == 5.0

    def test_daily_change_differs_from_tick_change(self):
        """The two metrics are genuinely different numbers and must not be conflated."""
        update = PriceUpdate(ticker="AAPL", price=199.5, previous_price=199.4, session_open=190.0)
        assert update.change == pytest.approx(0.1)
        assert update.daily_change == 9.5

    def test_negative_daily_change(self):
        """A price below the session open yields a negative daily change."""
        update = PriceUpdate(ticker="AAPL", price=180.5, previous_price=181.0, session_open=190.0)
        assert update.daily_change == -9.5
        assert update.daily_change_percent == -5.0

    def test_to_dict_includes_session_fields(self):
        """The SSE payload carries the baseline and both daily fields."""
        update = PriceUpdate(ticker="AAPL", price=199.5, previous_price=199.4, session_open=190.0)
        data = update.to_dict()
        assert data["session_open"] == 190.0
        assert data["daily_change"] == 9.5
        assert data["daily_change_percent"] == 5.0
