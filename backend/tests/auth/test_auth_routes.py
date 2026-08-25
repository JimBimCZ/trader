"""The six routes, against a real app with a mock provider."""

from __future__ import annotations

import dataclasses

import pytest

from app.auth.providers import OAuthProfile
from app.identity import COOKIE_NAME
from tests.conftest import CLIENT_BASE_URL, _drop_schema


@pytest.fixture
def configured_settings(settings):
    return dataclasses.replace(settings, google_client_id="id", google_client_secret="secret")


@pytest.fixture
def auth_client(configured_settings, monkeypatch):
    """A client whose provider exchange is stubbed at the seam.

    Only `_complete_exchange` is replaced -- everything below it (the decision,
    the store writes, the cookie) is the real code path. Stubbing at the route
    level instead would test the mock.
    """
    import asyncio

    from fastapi.testclient import TestClient

    from app.auth import router as router_module
    from app.main import create_app

    profile = OAuthProfile(
        provider="google", subject="sub-1", email="a@b.c", name="Ada", avatar=None
    )

    async def fake_exchange(request, provider):
        return dataclasses.replace(profile, provider=provider, subject=request.query_params["sub"])

    monkeypatch.setattr(router_module, "_complete_exchange", fake_exchange)
    try:
        with TestClient(create_app(configured_settings), base_url=CLIENT_BASE_URL) as client:
            yield client
    finally:
        # Mirrors `api_client`: the app closes its own pool in the lifespan,
        # but the throwaway schema outlives it. Left undropped, it and its
        # `users_profile`/`oauth_identities` tables linger for the rest of
        # the session and inflate unrelated `information_schema` counts in
        # later tests -- see tests/db/test_identity_schema.py.
        asyncio.run(_drop_schema(configured_settings.database_url, configured_settings.db_schema))


class TestProviders:
    def test_lists_only_what_is_configured(self, auth_client):
        body = auth_client.get("/api/auth/providers").json()
        assert body == {"providers": [{"name": "google", "label": "Google"}]}

    def test_an_unconfigured_deployment_lists_none(self, api_client):
        assert api_client.get("/api/auth/providers").json() == {"providers": []}

    def test_login_for_an_unconfigured_provider_is_404(self, api_client):
        response = api_client.get("/api/auth/login/google", follow_redirects=False)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"


class TestMe:
    def test_a_first_visit_is_a_guest(self, api_client):
        body = api_client.get("/api/auth/me").json()
        assert body["kind"] == "guest"
        assert body["email"] is None
        assert body["hasActivity"] is False

    def test_it_mints_a_session(self, api_client):
        """/api/auth/me is an ordinary user-resolving route -- the frontend
        calls it on mount, and that call is what gives a first-time visitor
        their guest."""
        assert api_client.get("/api/auth/me").status_code == 200
        assert COOKIE_NAME in api_client.cookies


def _session_cookies(response) -> list[str]:
    """Every `Set-Cookie: trader_session=...` on a response, not just the last.

    A route that accidentally also depended on `CurrentUserDep` would emit a
    second one naming the old user -- see the module docstring on
    `app.auth.router`. This is what makes that regression fail loudly instead
    of only in code review.
    """
    return [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{COOKIE_NAME}=")
    ]


class TestCallback:
    def test_a_new_identity_promotes_the_guest_in_place(self, auth_client):
        before = auth_client.get("/api/auth/me").json()
        response = auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/"
        assert len(_session_cookies(response)) == 1
        after = auth_client.get("/api/auth/me").json()
        assert after["id"] == before["id"]
        assert after["kind"] == "user"
        assert after["email"] == "a@b.c"

    def test_signing_in_again_from_a_clean_guest_switches_silently(self, auth_client):
        auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        signed_in = auth_client.get("/api/auth/me").json()

        auth_client.post("/api/auth/logout")
        fresh_guest = auth_client.get("/api/auth/me").json()
        assert fresh_guest["id"] != signed_in["id"]

        auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        assert auth_client.get("/api/auth/me").json()["id"] == signed_in["id"]

    def test_a_used_guest_is_asked_before_being_discarded(self, auth_client):
        auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        signed_in = auth_client.get("/api/auth/me").json()
        auth_client.post("/api/auth/logout")

        auth_client.post("/api/watchlist", json={"ticker": "PYPL"})
        contested = auth_client.get("/api/auth/me").json()

        response = auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"].startswith("/?claim=conflict&token=")
        # No Set-Cookie at all: the guest keeps its session, untouched, until
        # it confirms via /api/auth/claim (D-2).
        assert len(_session_cookies(response)) == 0
        assert auth_client.get("/api/auth/me").json()["id"] == contested["id"]

        token = response.headers["location"].split("token=")[1]
        claim_response = auth_client.post("/api/auth/claim", json={"token": token})
        assert claim_response.status_code == 200
        # A body, not just a status code: an empty 200 here is what let a
        # `SyntaxError` from `response.json()` reach the frontend as an
        # unhandled failure on every successful claim, even though the
        # cookie had already moved. See test_client.test.ts for the layer
        # that exercises the real fetch/json path this regressed in.
        assert claim_response.json() == {"ok": True}
        assert auth_client.get("/api/auth/me").json()["id"] == signed_in["id"]


class TestClaimRejection:
    def test_a_token_from_another_session_is_refused(self, auth_client, configured_settings):
        from app.auth.claim import ClaimToken

        forged = ClaimToken(configured_settings.session_secret).sign("someone-else", "user-9")
        response = auth_client.post("/api/auth/claim", json={"token": forged})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CLAIM_TOKEN_INVALID"


class TestLogout:
    def test_the_next_request_is_a_fresh_guest(self, api_client):
        first = api_client.get("/api/auth/me").json()["id"]
        api_client.post("/api/auth/logout")
        assert api_client.get("/api/auth/me").json()["id"] != first
