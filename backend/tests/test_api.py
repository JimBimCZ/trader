"""End-to-end tests over the HTTP surface, against a real started app."""

from __future__ import annotations

import pytest


class TestHealth:
    def test_reports_readiness_detail(self, api_client):
        """Health carries enough detail for E2E to wait on it."""
        body = api_client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["market_source"] == "simulator"
        assert body["tracked_tickers"] == 10
        assert body["db_ok"] is True
        assert body["seconds_since_last_tick"] < 30


class TestWatchlistRoutes:
    def test_lists_the_seeded_watchlist_without_prices(self, api_client):
        """Prices come from SSE only, so this response carries none."""
        body = api_client.get("/api/watchlist").json()
        assert len(body["tickers"]) == 10
        assert body["cap"] == 25
        assert isinstance(body["tickers"][0], str)

    def test_adds_and_removes(self, api_client):
        assert (
            "PYPL" in api_client.post("/api/watchlist", json={"ticker": "pypl"}).json()["tickers"]
        )
        assert "PYPL" not in api_client.delete("/api/watchlist/PYPL").json()["tickers"]

    def test_invalid_ticker_returns_the_envelope(self, api_client):
        response = api_client.post("/api/watchlist", json={"ticker": "BRK.B"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_TICKER"

    def test_removing_an_absent_ticker_is_404(self, api_client):
        response = api_client.delete("/api/watchlist/PYPL")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"

    def test_a_missing_body_field_is_422_in_the_envelope(self, api_client):
        response = api_client.post("/api/watchlist", json={})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestPortfolioRoutes:
    def test_starts_with_ten_thousand_in_cash(self, api_client):
        body = api_client.get("/api/portfolio").json()
        assert body["cash_balance"] == 10_000.0
        assert body["positions"] == []

    def test_buy_then_sell_round_trip(self, api_client):
        buy = api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10}
        ).json()
        assert buy["position"]["quantity"] == 10
        assert buy["cash_balance"] < 10_000.0

        sell = api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 10}
        ).json()
        assert sell["position"] is None
        assert sell["realized_pnl"] is not None

    def test_insufficient_cash_returns_the_code(self, api_client):
        response = api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 100_000}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INSUFFICIENT_CASH"

    def test_a_bad_side_is_rejected_by_the_schema(self, api_client):
        response = api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "hold", "quantity": 1}
        )
        assert response.status_code == 422

    def test_history_has_a_point_from_startup(self, api_client):
        """The writer records at t=0 so the chart is never empty."""
        snapshots = api_client.get("/api/portfolio/history").json()["snapshots"]
        assert len(snapshots) >= 1
        assert snapshots[0]["total_value"] == 10_000.0

    def test_history_limit_is_bounded(self, api_client):
        assert api_client.get("/api/portfolio/history?limit=0").status_code == 422
        assert api_client.get("/api/portfolio/history?limit=99999").status_code == 422


class TestHistoryRoute:
    def test_returns_points_for_a_tracked_ticker(self, api_client):
        body = api_client.get("/api/history/AAPL").json()
        assert body["ticker"] == "AAPL"
        assert len(body["points"]) >= 1
        assert set(body["points"][0]) == {"timestamp", "price"}

    def test_unknown_ticker_is_404(self, api_client):
        response = api_client.get("/api/history/ZZZZ")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TICKER_NOT_FOUND"


class TestChatRoutes:
    def test_history_starts_empty(self, api_client):
        assert api_client.get("/api/chat").json()["messages"] == []

    def test_a_mocked_trade_executes_inline(self, api_client):
        body = api_client.post("/api/chat", json={"message": "buy 10 shares of AAPL"}).json()
        assert body["error"] is False
        assert body["actions"][0]["status"] == "ok"
        assert api_client.get("/api/portfolio").json()["positions"][0]["ticker"] == "AAPL"

    def test_history_persists_the_conversation(self, api_client):
        api_client.post("/api/chat", json={"message": "hello"})
        messages = api_client.get("/api/chat").json()["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant"]

    def test_an_upstream_failure_is_still_a_200(self, api_client):
        """The chat panel needs no separate error path."""
        response = api_client.post("/api/chat", json={"message": "__mock_error__"})
        assert response.status_code == 200
        assert response.json()["error"] is True

    def test_an_empty_message_is_rejected(self, api_client):
        assert api_client.post("/api/chat", json={"message": ""}).status_code == 422


class TestResetRoute:
    def test_restores_the_seeded_state(self, api_client):
        api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 5}
        )
        api_client.post("/api/chat", json={"message": "hello"})
        api_client.post("/api/watchlist", json={"ticker": "PYPL"})

        body = api_client.post("/api/reset").json()

        assert body["cash_balance"] == 10_000.0
        assert body["positions"] == []
        assert api_client.get("/api/chat").json()["messages"] == []
        assert len(api_client.get("/api/watchlist").json()["tickers"]) == 10


class TestStaticServing:
    def test_api_routes_are_not_shadowed_by_the_spa_fallback(self, api_client):
        """The catch-all must never swallow an API path."""
        assert api_client.get("/api/health").json()["status"] == "ok"

    def test_a_missing_frontend_reports_a_build_problem(self, api_client):
        """Without a built export the fallback says so rather than 404ing."""
        response = api_client.get("/some/spa/route")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "FRONTEND_NOT_BUILT"


@pytest.mark.parametrize("path", ["/api/portfolio", "/api/watchlist", "/api/chat", "/api/health"])
def test_every_get_route_answers(api_client, path):
    """Smoke check that no route is broken by wiring changes."""
    assert api_client.get(path).status_code == 200
