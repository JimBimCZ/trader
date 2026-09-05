"""ResetService's demo branch: what a guest gets back, and what a signed-in
account does not.

The shared `settings` fixture pins `demo_portfolio=False` (tests/conftest.py),
so "a guest's reset restores the demo" and its converse for a signed-in
account had no cover of their own -- only inspection.
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
    """The demo on for this deployment, and one provider configured so a
    guest can be promoted to a signed-in account within the same test."""
    return dataclasses.replace(
        settings, demo_portfolio=True, google_client_id="id", google_client_secret="secret"
    )


@pytest.fixture
def demo_client(demo_settings, monkeypatch):
    from app.auth import router as router_module

    profile = OAuthProfile(
        provider="google", subject="sub-1", email="a@b.c", name="Ada", avatar=None
    )

    async def fake_exchange(request, provider):
        return profile

    monkeypatch.setattr(router_module, "_complete_exchange", fake_exchange)
    try:
        with TestClient(create_app(demo_settings), base_url=CLIENT_BASE_URL) as client:
            yield client
    finally:
        asyncio.run(_drop_schema(demo_settings.database_url, demo_settings.db_schema))


class TestResetDemoBranch:
    def test_a_guests_reset_restores_the_demo(self, demo_client):
        """reset()'s demo=True path: a guest's reset is the one case where
        handing back a portfolio the user never placed is correct -- the
        demo IS their seeded starting state."""
        demo_client.get("/api/portfolio")  # mints the guest and its demo

        body = demo_client.post("/api/reset").json()

        assert len(body["positions"]) == 4
        assert body["cash_balance"] == 4099.00

    def test_a_signed_in_users_reset_stays_clean(self, demo_client, demo_settings):
        """reset()'s demo=False path: once the account is real, its reset
        must not hand the demo back, even though demo_portfolio is on for
        this deployment."""
        demo_client.get("/api/portfolio")  # mints the guest and its demo
        demo_client.get("/api/auth/callback/google", follow_redirects=False)  # promotes it

        body = demo_client.post("/api/reset").json()

        assert body["positions"] == []
        assert body["cash_balance"] == demo_settings.initial_cash
