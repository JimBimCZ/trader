"""Reset wipes one user, and reconciles for everyone."""

from __future__ import annotations


class TestResetTouchesOnlyTheCaller:
    def test_another_user_keeps_their_watchlist_edits(self, api_client, second_client):
        second_client.post("/api/watchlist", json={"ticker": "PYPL"})

        api_client.post("/api/reset")

        assert "PYPL" in second_client.get("/api/watchlist").json()["tickers"]

    def test_another_user_keeps_their_cash(self, api_client, second_client):
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 2, "side": "buy"},
        )
        spent = second_client.get("/api/portfolio").json()["cash_balance"]

        api_client.post("/api/reset")

        assert second_client.get("/api/portfolio").json()["cash_balance"] == spent

    def test_the_caller_is_restored_to_the_seeded_state(self, api_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 2, "side": "buy"},
        )

        body = api_client.post("/api/reset").json()

        assert body["cash_balance"] == 10000.0
        assert body["positions"] == []
        assert len(api_client.get("/api/watchlist").json()["tickers"]) == 10


class TestResetKeepsOthersTracked:
    def test_a_ticker_another_user_holds_stays_priced_after_a_reset(
        self, api_client, second_client
    ):
        """Reset releases the caller's tickers; a global reconcile is what
        stops that from evicting a price someone else's position needs."""
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "NVDA", "quantity": 1, "side": "buy"},
        )

        api_client.post("/api/reset")

        portfolio = second_client.get("/api/portfolio").json()
        assert portfolio["positions"][0]["current_price"] is not None
