"""Idle guests expire; signed-in users never do."""

from __future__ import annotations


class TestCleanupRoute:
    def test_the_route_is_refused_without_the_secret(self, api_client):
        assert api_client.post("/api/admin/cleanup").status_code in (401, 403)

    def test_the_route_is_refused_with_the_wrong_secret(self, api_client):
        response = api_client.post("/api/admin/cleanup", headers={"X-Cleanup-Secret": "wrong"})
        assert response.status_code in (401, 403)


class TestCleaner:
    async def test_run_once_deletes_only_expired_guests(self, seeded_db, settings):
        from app.identity.store import UserStore
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
