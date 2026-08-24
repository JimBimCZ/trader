"""User A must not read or mutate user B's rows.

The highest-value tests in this suite. Every other test checks that a feature
works; these check that it does not work on someone else's data. A regression
here is not a bug report, it is a privacy incident -- so they drive two real
HTTP sessions rather than two hand-built repositories, because the scoping has
to hold through the whole dependency chain.
"""

from __future__ import annotations


class TestPortfolioIsolation:
    def test_a_trade_by_one_user_is_invisible_to_another(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
        )

        other = second_client.get("/api/portfolio").json()

        assert other["positions"] == []
        assert other["cash_balance"] == 10000.0

    def test_spending_cash_does_not_spend_anyone_else_s(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 1, "side": "buy"},
        )

        assert api_client.get("/api/portfolio").json()["cash_balance"] < 10000.0
        assert second_client.get("/api/portfolio").json()["cash_balance"] == 10000.0


class TestWatchlistIsolation:
    def test_an_added_ticker_does_not_appear_for_another_user(self, api_client, second_client):
        api_client.post("/api/watchlist", json={"ticker": "PYPL"})

        assert "PYPL" not in second_client.get("/api/watchlist").json()["tickers"]

    def test_a_removed_ticker_stays_for_another_user(self, api_client, second_client):
        api_client.delete("/api/watchlist/AAPL")

        assert "AAPL" in second_client.get("/api/watchlist").json()["tickers"]


class TestChatIsolation:
    def test_chat_history_is_not_shared(self, api_client, second_client):
        api_client.post("/api/chat", json={"message": "isolation probe"})

        theirs = second_client.get("/api/chat").json()

        assert all("isolation probe" not in m["content"] for m in theirs["messages"])


class TestResetIsolation:
    def test_a_reset_does_not_wipe_another_user(self, api_client, second_client):
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 3, "side": "buy"},
        )

        api_client.post("/api/reset")

        survivor = second_client.get("/api/portfolio").json()
        assert len(survivor["positions"]) == 1
        assert survivor["positions"][0]["ticker"] == "AAPL"

    def test_a_reset_does_not_blank_the_shared_price_history(self, api_client):
        """The ring buffer holds market data per ticker, shared by everyone.

        Clearing it on reset blanked the main chart for every other user, who
        had asked for nothing. Asserted on a ticker the market source does not
        track, because the collector refills a real one within a poll interval
        -- which would make this pass whether the bug was there or not.
        """
        store = api_client.app.state.history_store
        store.track("ZZZZ")
        store.append("ZZZZ", 1.0, 100.0)

        api_client.post("/api/reset")

        assert store.get("ZZZZ") == [(1.0, 100.0)]
