"""Reset must not leave the profile row committed-absent, even briefly.

Migration 001 attached a foreign key from every per-user table to
`users_profile`. `reset()` used to delete the profile in one transaction and
re-seed it in a second, so between the two there was a genuinely committed
window with no profile row. `ChatService.send_message` inserts its user
message under neither of the locks `reset()` holds and outside
`transaction()`, so nothing serialized it against that window -- an insert
landing there now raises ForeignKeyViolationError and surfaces as a 500.
Before the foreign keys existed the same race silently wrote an orphan row.

Reset no longer deletes the profile at all -- it updates the cash balance in
place, because deleting it would cascade the user out of existence and
invalidate the cookie that is the only pointer to their rows. This test still
observes the window, from a second connection at the one instant that
matters, so a return to delete-then-recreate cannot pass unnoticed.
"""

from __future__ import annotations

import asyncpg
import pytest

import app.system.service as reset_module
from app.db.postgres import normalize_dsn


@pytest.fixture
def observed_profile_during_reset(settings, monkeypatch):
    """Record whether the profile is visible to another connection mid-reset."""
    seen: list[int] = []
    real_seed = reset_module.seed_user

    async def observing_seed(db, config, user_id):
        observer = await asyncpg.connect(
            normalize_dsn(settings.database_url),
            server_settings={"search_path": settings.db_schema},
        )
        try:
            row = await observer.fetchrow(
                "SELECT count(*) AS n FROM users_profile WHERE id = $1", user_id
            )
            seen.append(row["n"])
        finally:
            await observer.close()
        return await real_seed(db, config, user_id)

    monkeypatch.setattr(reset_module, "seed_user", observing_seed)
    return seen


class TestResetIsAtomic:
    def test_the_profile_is_never_committed_absent(self, api_client, observed_profile_during_reset):
        response = api_client.post("/api/reset")
        assert response.status_code == 200

        assert observed_profile_during_reset, "seed_user was never reached"
        assert observed_profile_during_reset == [1], (
            "another connection saw users_profile empty during reset -- the "
            "delete was committed before the re-seed, so a concurrent "
            "FK-bearing insert would fail"
        )

    def test_reset_still_leaves_a_usable_seeded_state(self, api_client):
        assert api_client.post("/api/reset").status_code == 200

        portfolio = api_client.get("/api/portfolio").json()
        assert portfolio["cash_balance"] == 10000.0
        assert portfolio["positions"] == []
        assert len(api_client.get("/api/watchlist").json()["tickers"]) == 10
