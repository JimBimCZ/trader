"""What signing in does to a seeded demo portfolio.

The rule has two conditions and both are load-bearing (design doc §5).
`test_a_second_provider_on_an_existing_account_keeps_everything` is the one
that matters most: without the guest check, connecting GitHub to an account
that already signed in with Google would delete a real portfolio.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import OAuthProfile
from app.main import create_app
from tests.conftest import CLIENT_BASE_URL, _drop_schema


@pytest.fixture
def demo_settings(settings):
    """OAuth configured, and the demo portfolio on — which is the default."""
    return dataclasses.replace(
        settings,
        google_client_id="id",
        google_client_secret="secret",
        github_client_id="gh-id",
        github_client_secret="gh-secret",
        demo_portfolio=True,
    )


@pytest.fixture
def auth_client(demo_settings, monkeypatch):
    from app.auth import router as router_module

    profile = OAuthProfile(
        provider="google", subject="sub-1", email="a@b.c", name="Ada", avatar=None
    )

    async def fake_exchange(request, provider):
        return dataclasses.replace(profile, provider=provider, subject=request.query_params["sub"])

    monkeypatch.setattr(router_module, "_complete_exchange", fake_exchange)
    try:
        with TestClient(create_app(demo_settings), base_url=CLIENT_BASE_URL) as client:
            yield client
    finally:
        asyncio.run(_drop_schema(demo_settings.database_url, demo_settings.db_schema))


def _portfolio(client) -> dict:
    return client.get("/api/portfolio").json()


def _sign_in(client, provider: str = "google", sub: str = "sub-1"):
    return client.get(f"/api/auth/callback/{provider}?sub={sub}", follow_redirects=False)


class TestDemoClearing:
    def test_a_guest_starts_on_the_demo(self, auth_client, demo_settings):
        """The premise every other test here rests on."""
        before = _portfolio(auth_client)
        assert len(before["positions"]) == 4
        assert before["cash_balance"] == 4099.00

    def test_an_untouched_guest_loses_the_demo_on_sign_in(self, auth_client, demo_settings):
        """The showroom is not what an account should start as."""
        _portfolio(auth_client)  # mints the guest and its demo
        _sign_in(auth_client)

        after = _portfolio(auth_client)
        assert after["positions"] == []
        assert after["cash_balance"] == demo_settings.initial_cash
        assert auth_client.get("/api/portfolio/trades").json()["trades"] == []
        assert auth_client.get("/api/auth/me").json()["kind"] == "user"

    def test_a_guest_who_traded_keeps_their_portfolio(self, auth_client):
        """PROMOTE exists to carry a guest's work into their account."""
        _portfolio(auth_client)
        auth_client.post(
            "/api/portfolio/trade",
            json={"ticker": "GOOGL", "side": "buy", "quantity": 1},
        )
        _sign_in(auth_client)

        after = _portfolio(auth_client)
        assert any(p["ticker"] == "GOOGL" for p in after["positions"])
        assert len(after["positions"]) == 5

    def test_a_second_provider_on_an_existing_account_keeps_everything(self, auth_client):
        """The edge that makes the guest check non-negotiable.

        PROMOTE fires here too -- a signed-in session, an identity nothing is
        linked to yet -- and `decide()` reports session_has_activity=False,
        because it only computes that value for guests. A rule keyed on
        activity alone would read that False and delete this user's holdings.
        """
        _portfolio(auth_client)
        _sign_in(auth_client, "google", "sub-1")
        auth_client.post(
            "/api/portfolio/trade",
            json={"ticker": "GOOGL", "side": "buy", "quantity": 2},
        )
        held = _portfolio(auth_client)["positions"]
        assert held != []

        # Same browser, same account, second provider.
        _sign_in(auth_client, "github", "gh-sub-1")

        assert _portfolio(auth_client)["positions"] == held

    def test_signing_in_on_a_fresh_browser_creates_a_clean_account(self, auth_client):
        """CREATE mints a guest to build on, so it seeds a demo too -- and
        must clear it for exactly the same reason PROMOTE does."""
        auth_client.post("/api/auth/logout")
        _sign_in(auth_client, "google", "sub-new")

        after = _portfolio(auth_client)
        assert after["positions"] == []
