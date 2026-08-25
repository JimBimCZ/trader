"""Cookie -> user resolution, and the routes that must not mint one."""

from __future__ import annotations

import dataclasses

import pytest

from app.identity import COOKIE_NAME


@pytest.fixture
def bounded_stream_client(settings):
    """A client whose SSE stream closes itself, so a test can read it whole."""
    import asyncio

    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import CLIENT_BASE_URL, _drop_schema

    bounded = dataclasses.replace(settings, stream_max_seconds=0.05)
    try:
        with TestClient(create_app(bounded), base_url=CLIENT_BASE_URL) as client:
            yield client
    finally:
        asyncio.run(_drop_schema(bounded.database_url, bounded.db_schema))


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

    def test_the_price_stream_does_not_mint_a_guest(self, bounded_stream_client):
        """The other exempt route. A long-lived EventSource that minted on
        connect would create a row for every reconnect, forever.

        Driven through a client whose stream closes itself after 50ms: the
        stream is otherwise endless, and TestClient runs the app in a portal
        that waits for the response generator to finish.
        """
        response = bounded_stream_client.get("/api/stream/prices")

        assert response.status_code == 200
        assert "set-cookie" not in response.headers
        assert COOKIE_NAME not in response.cookies


class TestSecureFlagFollowsTheScheme:
    """`Secure` keyed off the hostname was the bug this replaces.

    A browser refuses to store or return a Secure cookie over plain http, so
    "secure everywhere except localhost" meant a Docker deployment reached on
    a LAN address dropped the cookie on every response and minted a fresh
    guest on every single request -- unbounded rows, a portfolio that reset
    constantly, and nothing raising.
    """

    def test_a_plain_http_request_gets_no_secure_flag(self, api_client):
        """A LAN address, not localhost -- localhost was exempt either way,
        so asserting on it would pass against the bug this replaces."""
        response = api_client.get("http://192.168.1.5/api/portfolio")

        assert "Secure" not in response.headers["set-cookie"]

    def test_an_https_request_gets_the_secure_flag(self, api_client):
        response = api_client.get("https://localhost/api/portfolio")

        assert "Secure" in response.headers["set-cookie"]

    def test_a_proxy_forwarding_https_gets_the_secure_flag(self, api_client):
        """Vercel terminates TLS upstream, so the app itself sees plain http."""
        response = api_client.get(
            "http://localhost/api/portfolio", headers={"X-Forwarded-Proto": "https"}
        )

        assert "Secure" in response.headers["set-cookie"]

    def test_the_first_hop_of_a_proxy_chain_wins(self, api_client):
        """A chain lists schemes oldest-first; the browser's is the first."""
        response = api_client.get(
            "http://localhost/api/portfolio", headers={"X-Forwarded-Proto": "https, http"}
        )

        assert "Secure" in response.headers["set-cookie"]

    def test_a_proxy_forwarding_plain_http_gets_no_secure_flag(self, api_client):
        response = api_client.get(
            "http://localhost/api/portfolio", headers={"X-Forwarded-Proto": "http"}
        )

        assert "Secure" not in response.headers["set-cookie"]
