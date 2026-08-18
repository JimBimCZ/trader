"""Tests for the price history ring buffer."""

from __future__ import annotations

from app.history import HistoryStore


class TestAppend:
    def test_records_points_oldest_first(self):
        store = HistoryStore(maxlen=10)
        store.append("AAPL", 1.0, 190.0)
        store.append("AAPL", 2.0, 191.0)
        assert store.get("AAPL") == [(1.0, 190.0), (2.0, 191.0)]

    def test_evicts_the_oldest_point_when_full(self):
        """The buffer is bounded, so a long-running container cannot grow."""
        store = HistoryStore(maxlen=3)
        for i in range(5):
            store.append("AAPL", float(i), 100.0 + i)
        assert store.get("AAPL") == [(2.0, 102.0), (3.0, 103.0), (4.0, 104.0)]

    def test_skips_a_repeated_timestamp(self):
        """The collector polls faster than some sources tick.

        Recording the same point twice would flat-line the chart with fake
        data rather than showing a genuine gap.
        """
        store = HistoryStore(maxlen=10)
        store.append("AAPL", 1.0, 190.0)
        store.append("AAPL", 1.0, 190.0)
        assert len(store.get("AAPL")) == 1

    def test_tickers_are_independent(self):
        store = HistoryStore(maxlen=10)
        store.append("AAPL", 1.0, 190.0)
        store.append("MSFT", 1.0, 420.0)
        assert store.get("AAPL") == [(1.0, 190.0)]
        assert store.get("MSFT") == [(1.0, 420.0)]


class TestGet:
    def test_unknown_ticker_returns_none(self):
        """None means never tracked, which the route reports as a 404."""
        assert HistoryStore().get("ZZZZ") is None

    def test_tracked_but_empty_returns_an_empty_list(self):
        """An empty list means tracked with no ticks yet, which is a 200."""
        store = HistoryStore()
        store.track("AAPL")
        assert store.get("AAPL") == []


class TestLifecycle:
    def test_drop_forgets_one_ticker(self):
        store = HistoryStore()
        store.append("AAPL", 1.0, 190.0)
        store.drop("AAPL")
        assert store.get("AAPL") is None

    def test_clear_forgets_everything(self):
        store = HistoryStore()
        store.append("AAPL", 1.0, 190.0)
        store.append("MSFT", 1.0, 420.0)
        store.clear()
        assert len(store) == 0

    def test_membership_and_length(self):
        store = HistoryStore()
        store.append("AAPL", 1.0, 190.0)
        assert "AAPL" in store
        assert len(store) == 1
