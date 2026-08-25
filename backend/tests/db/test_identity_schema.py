"""The identity tables, on a fresh database and on one that already exists."""

from __future__ import annotations

import pytest

from app.db import run_migrations


@pytest.mark.asyncio
class TestFreshSchema:
    async def test_oauth_identities_exists(self, db):
        row = await db.fetch_one(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            "WHERE table_name = 'oauth_identities'"
        )
        assert row["n"] == 1

    @pytest.mark.parametrize("column", ["email", "display_name", "avatar_url"])
    async def test_users_profile_carries_the_identity_columns(self, db, column):
        row = await db.fetch_one(
            "SELECT COUNT(*) AS n FROM information_schema.columns "
            "WHERE table_name = 'users_profile' AND column_name = $1",
            column,
        )
        assert row["n"] == 1


@pytest.mark.asyncio
class TestConstraints:
    async def test_one_identity_per_provider_subject(self, db, seeded_user_id):
        await db.execute(
            "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
            "created_at) VALUES ('google', 'sub-1', $1, 'a@b.c', '2026-01-01T00:00:00Z')",
            seeded_user_id,
        )
        with pytest.raises(Exception):
            await db.execute(
                "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
                "created_at) VALUES ('google', 'sub-1', $1, 'a@b.c', '2026-01-01T00:00:00Z')",
                seeded_user_id,
            )

    async def test_deleting_the_user_removes_the_identity(self, db, seeded_user_id):
        """Guest expiry is a single DELETE; an orphaned identity would let a
        deleted account be signed back into."""
        await db.execute(
            "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
            "created_at) VALUES ('github', 'sub-2', $1, NULL, '2026-01-01T00:00:00Z')",
            seeded_user_id,
        )
        await db.execute("DELETE FROM users_profile WHERE id = $1", seeded_user_id)
        row = await db.fetch_one("SELECT COUNT(*) AS n FROM oauth_identities")
        assert row["n"] == 0


@pytest.mark.asyncio
async def test_migrations_are_idempotent(db):
    """No version table records what has run, so every statement must survive
    a second execution -- which is what happens on every single startup."""
    await run_migrations(db)
    await run_migrations(db)
