"""The E2E sign-in shortcut, and the guard that keeps it out of production."""

from __future__ import annotations

import asyncio
import dataclasses

from fastapi.testclient import TestClient

from app.identity import COOKIE_NAME
from app.main import create_app
from tests.conftest import CLIENT_BASE_URL, _drop_schema


def _session_cookies(response) -> list[str]:
    """Every `Set-Cookie: trader_session=...` on a response, not just the last.

    A route that accidentally also depended on `CurrentUserDep` would emit a
    second one naming the old user. This ensures we're sending exactly one.
    """
    return [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{COOKIE_NAME}=")
    ]


class TestGuard:
    def test_it_is_absent_by_default(self, settings):
        """Not merely refused -- 404, the same answer an unconfigured provider
        gives, so a probe cannot tell the route exists at all.

        Probes an unknown user id, so falls through to the not-found branch.
        The guard test (below) isolates it with a known user.
        """
        try:
            with TestClient(create_app(settings), base_url=CLIENT_BASE_URL) as client:
                response = client.get("/api/auth/dev-login/anyone", follow_redirects=False)
                assert response.status_code == 404
                assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"
        finally:
            asyncio.run(_drop_schema(settings.database_url, settings.db_schema))

    def test_the_guard_blocks_known_users_when_disabled(self, settings):
        """The AUTH_MOCK guard itself: known user rejected when auth_mock=False.

        This isolates the guard from the unknown-user branch: creates a real
        user with AUTH_MOCK on, then tries to access it with AUTH_MOCK off
        and expects the guard to reject it with 404.
        """
        try:
            # Seed a user with auth_mock=True
            app1 = create_app(dataclasses.replace(settings, auth_mock=True))
            with TestClient(app1, base_url=CLIENT_BASE_URL) as client:
                user_id = client.get("/api/auth/me").json()["id"]

            # Try to access that user with auth_mock=False (the default)
            app2 = create_app(settings)  # auth_mock defaults to False
            with TestClient(app2, base_url=CLIENT_BASE_URL) as client:
                response = client.get(f"/api/auth/dev-login/{user_id}", follow_redirects=False)
                assert response.status_code == 404
                assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"
        finally:
            asyncio.run(_drop_schema(settings.database_url, settings.db_schema))


class TestEnabled:
    def test_it_signs_a_session_for_an_existing_user(self, settings):
        """Route works: existing user can be signed in."""
        try:
            with TestClient(
                create_app(dataclasses.replace(settings, auth_mock=True)),
                base_url=CLIENT_BASE_URL,
            ) as client:
                user_id = client.get("/api/auth/me").json()["id"]
                client.post("/api/auth/logout")
                assert client.get("/api/auth/me").json()["id"] != user_id

                response = client.get(f"/api/auth/dev-login/{user_id}", follow_redirects=False)
                assert response.status_code == 307
                assert response.headers["location"] == "/"
                assert len(_session_cookies(response)) == 1

                assert client.get("/api/auth/me").json()["id"] == user_id
        finally:
            asyncio.run(_drop_schema(settings.database_url, settings.db_schema))

    def test_an_unknown_user_is_refused(self, settings):
        """Unknown user ID rejected even with AUTH_MOCK on."""
        try:
            with TestClient(
                create_app(dataclasses.replace(settings, auth_mock=True)),
                base_url=CLIENT_BASE_URL,
            ) as client:
                response = client.get("/api/auth/dev-login/no-such-user", follow_redirects=False)
                assert response.status_code == 404
        finally:
            asyncio.run(_drop_schema(settings.database_url, settings.db_schema))
