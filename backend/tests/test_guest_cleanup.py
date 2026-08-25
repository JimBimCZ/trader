"""Idle guests expire; signed-in users never do."""

from __future__ import annotations

import dataclasses

import pytest_asyncio

from app.db import init_db
from app.db.postgres import PostgresDatabase
from app.identity.store import UserStore
from tests.conftest import CLIENT_BASE_URL, _drop_schema

#: Same length as the "wrong" secret below, so that test exercises
#: `secrets.compare_digest`'s constant-time byte comparison rather than an
#: early length mismatch, which would prove nothing about the comparison
#: itself.
CLEANUP_SECRET = "test-cleanup-secret-abcdefghijkl"
WRONG_SECRET_SAME_LENGTH = CLEANUP_SECRET[:-1] + ("x" if CLEANUP_SECRET[-1] != "x" else "y")


class TestCleanupRoute:
    def test_the_route_is_refused_without_the_secret(self, api_client):
        assert api_client.post("/api/admin/cleanup").status_code in (401, 403)

    def test_the_route_is_refused_with_the_wrong_secret(self, api_client):
        response = api_client.post("/api/admin/cleanup", headers={"X-Cleanup-Secret": "wrong"})
        assert response.status_code in (401, 403)


class TestCleaner:
    async def test_run_once_deletes_only_expired_guests(self, seeded_db, settings):
        from app.system.cleanup import GuestCleaner

        store = UserStore(seeded_db, settings)
        stale = await store.mint_guest()
        fresh = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", stale.id),
        )

        deleted = await GuestCleaner(store, settings).run_once()

        assert deleted == 1
        assert await store.get(stale.id) is None
        assert await store.get(fresh.id) is not None


async def _seed_expired_user(database: PostgresDatabase, settings, kind: str) -> str:
    """Insert a `users_profile` row that is already past the TTL.

    Goes through `UserStore.mint_guest` -- which always writes `kind='guest'`
    and seeds the row's watchlist/positions/etc. -- and then overwrites
    `kind`/`last_seen_at` directly, so a `kind='user'` row is reachable
    without a separate signed-in-user minting path.
    """
    store = UserStore(database, settings)
    user = await store.mint_guest()
    await database.execute(
        "UPDATE users_profile SET kind = ?, last_seen_at = ? WHERE id = ?",
        (kind, "2020-01-01T00:00:00Z", user.id),
    )
    return user.id


@pytest_asyncio.fixture
async def configured_settings(settings):
    """Same throwaway schema as `settings`, with a real `cleanup_secret`.

    Torn down here (schema drop) regardless of whether a given test ever
    opens a raw connection of its own -- some only build a `TestClient`,
    whose lifespan creates the schema itself.
    """
    configured = dataclasses.replace(settings, cleanup_secret=CLEANUP_SECRET)
    yield configured
    await _drop_schema(configured.database_url, configured.db_schema)


@pytest_asyncio.fixture
async def configured_client(configured_settings):
    """A `TestClient` whose app has a real `cleanup_secret` configured."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(configured_settings), base_url=CLIENT_BASE_URL) as client:
        yield client


class TestCleanupRouteWithSecretConfigured:
    """`TestCleanupRoute` above only ever runs against the default settings,
    where `cleanup_secret == ""` -- every request there is refused by the
    `not secret` short-circuit before `compare_digest` is ever reached, the
    success path through the HTTP route is never exercised (`TestCleaner`
    calls `GuestCleaner.run_once()` directly, bypassing the route), and GET
    is never exercised even though GET/POST parity is the point of the task.
    These configure a real secret so each of those is an assertion rather
    than something proven only by reading the code.
    """

    async def test_post_with_the_correct_secret_deletes_only_expired_guests(
        self, configured_settings
    ):
        """The success path through the route, with a genuinely non-zero
        count, and confirmation that a `kind='user'` row survives a cleanup
        run *through the route* -- the property most expensive to get wrong,
        since a cron will call the route, not `run_once()` directly."""
        database = await PostgresDatabase.connect(
            configured_settings.database_url, search_path=configured_settings.db_schema
        )
        try:
            await init_db(database)
            expired_guest_id = await _seed_expired_user(database, configured_settings, "guest")
            expired_user_id = await _seed_expired_user(database, configured_settings, "user")
        finally:
            await database.close()

        from fastapi.testclient import TestClient

        from app.main import create_app

        with TestClient(create_app(configured_settings), base_url=CLIENT_BASE_URL) as client:
            response = client.post(
                "/api/admin/cleanup", headers={"X-Cleanup-Secret": CLEANUP_SECRET}
            )

        assert response.status_code == 200
        assert response.json() == {"deleted": 1}

        verify = await PostgresDatabase.connect(
            configured_settings.database_url, search_path=configured_settings.db_schema
        )
        try:
            rows = await verify.fetch_all("SELECT id FROM users_profile")
        finally:
            await verify.close()

        remaining_ids = {row["id"] for row in rows}
        assert expired_guest_id not in remaining_ids, "the expired guest should have been deleted"
        assert expired_user_id in remaining_ids, "a signed-in user must never expire"

    async def test_post_with_a_wrong_secret_of_the_same_length_is_refused(self, configured_client):
        response = configured_client.post(
            "/api/admin/cleanup", headers={"X-Cleanup-Secret": WRONG_SECRET_SAME_LENGTH}
        )
        assert response.status_code in (401, 403)

    async def test_get_with_the_correct_secret_succeeds_identically(self, configured_client):
        """GET is what Vercel Cron actually issues. Proves GET/POST parity
        by assertion instead of leaving it true only by construction."""
        response = configured_client.get(
            "/api/admin/cleanup", headers={"X-Cleanup-Secret": CLEANUP_SECRET}
        )

        assert response.status_code == 200
        assert response.json() == {"deleted": 0}

    async def test_the_route_is_refused_when_the_header_is_entirely_absent(self, configured_client):
        """A secret is configured, but the caller sent no header at all --
        distinct from the unset-secret case in `TestCleanupRoute`."""
        response = configured_client.post("/api/admin/cleanup")
        assert response.status_code in (401, 403)


class TestCleanupRouteAcceptsVercelsBearerHeader:
    """Vercel Cron cannot be configured to send a custom header -- its own
    mechanism is `Authorization: Bearer <CRON_SECRET>`, auto-attached to
    every invocation. The route must accept that alongside `X-Cleanup-Secret`
    (which a human or a non-Vercel scheduler sends), against the same
    configured secret -- otherwise the shipped Cron entry gets 403 forever
    and idle guests accumulate without bound on a Vercel deployment.
    """

    async def test_get_with_the_correct_bearer_token_succeeds(self, configured_client):
        response = configured_client.get(
            "/api/admin/cleanup", headers={"Authorization": f"Bearer {CLEANUP_SECRET}"}
        )
        assert response.status_code == 200
        assert response.json() == {"deleted": 0}

    async def test_a_same_length_wrong_bearer_token_is_refused(self, configured_client):
        response = configured_client.post(
            "/api/admin/cleanup",
            headers={"Authorization": f"Bearer {WRONG_SECRET_SAME_LENGTH}"},
        )
        assert response.status_code in (401, 403)

    async def test_a_malformed_authorization_header_is_refused(self, configured_client):
        """No `Bearer ` prefix at all -- not just a wrong token."""
        response = configured_client.post(
            "/api/admin/cleanup", headers={"Authorization": CLEANUP_SECRET}
        )
        assert response.status_code in (401, 403)
