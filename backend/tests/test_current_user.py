"""Cookie -> user resolution, and the routes that must not mint one."""

from __future__ import annotations

from app.identity import COOKIE_NAME


class TestGuestMinting:
    def test_a_first_request_mints_a_guest_and_sets_the_cookie(self, api_client):
        response = api_client.get("/api/portfolio")

        assert response.status_code == 200
        assert COOKIE_NAME in response.cookies

    def test_the_cookie_is_httponly_lax_and_long_lived(self, api_client):
        response = api_client.get("/api/portfolio")

        header = response.headers["set-cookie"]
        assert "HttpOnly" in header
        assert "SameSite=Lax" in header
        assert "Max-Age=7776000" in header

    def test_the_same_cookie_returns_the_same_user(self, api_client):
        """The client keeps the cookie, so the second call must not mint."""
        api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"}
        )

        portfolio = api_client.get("/api/portfolio").json()

        assert len(portfolio["positions"]) == 1

    def test_a_tampered_cookie_gets_a_fresh_guest_rather_than_an_error(self, api_client):
        api_client.cookies.set(COOKIE_NAME, "not-a-valid-signature")

        response = api_client.get("/api/portfolio")

        assert response.status_code == 200
        assert response.json()["cash_balance"] == 10000.0


class TestExemptRoutes:
    def test_health_does_not_mint_a_guest(self, api_client):
        """Every uptime probe would otherwise create a row."""
        response = api_client.get("/api/health")

        assert response.status_code == 200
        assert COOKIE_NAME not in response.cookies

    def test_health_still_works_with_no_users_at_all(self, api_client):
        assert api_client.get("/api/health").json()["status"] == "ok"
