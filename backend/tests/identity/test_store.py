"""Guest minting, seeding, and the last_seen_at throttle."""

from __future__ import annotations

from app.identity.store import UserStore


class TestMinting:
    async def test_a_minted_guest_starts_with_cash_and_the_default_watchlist(
        self, seeded_db, settings
    ):
        store = UserStore(seeded_db, settings)

        user = await store.mint_guest()

        assert user.kind == "guest"
        assert user.cash_balance == settings.initial_cash
        rows = await seeded_db.fetch_all(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (user.id,)
        )
        assert len(rows) == 10

    async def test_two_guests_get_separate_rows_and_separate_watchlists(self, seeded_db, settings):
        store = UserStore(seeded_db, settings)

        first = await store.mint_guest()
        second = await store.mint_guest()

        assert first.id != second.id
        for user in (first, second):
            rows = await seeded_db.fetch_all(
                "SELECT ticker FROM watchlist WHERE user_id = ?", (user.id,)
            )
            assert len(rows) == 10

    async def test_a_minted_guest_can_be_loaded_back(self, seeded_db, settings):
        store = UserStore(seeded_db, settings)
        minted = await store.mint_guest()

        loaded = await store.get(minted.id)

        assert loaded is not None
        assert loaded.id == minted.id
        assert loaded.kind == "guest"

    async def test_an_unknown_id_loads_as_none(self, seeded_db, settings):
        """A cookie signed before a database reset points at a row that is
        gone; that must mint a fresh guest, not raise."""
        assert await UserStore(seeded_db, settings).get("no-such-user") is None


class TestTouchThrottle:
    async def test_the_first_touch_after_the_window_writes(self, seeded_db, settings):
        store = UserStore(seeded_db, settings)
        user = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user.id),
        )
        stale = await store.get(user.id)

        await store.touch(stale)

        refreshed = await store.get(user.id)
        assert refreshed.last_seen_at != "2020-01-01T00:00:00+00:00"

    async def test_a_touch_inside_the_window_does_not_write(self, seeded_db, settings):
        """Unthrottled, every GET becomes a write -- a Neon round trip per
        read on the hottest path in the app."""
        store = UserStore(seeded_db, settings)
        user = await store.mint_guest()
        before = (await store.get(user.id)).last_seen_at

        await store.touch(await store.get(user.id))

        assert (await store.get(user.id)).last_seen_at == before


class TestExpiry:
    async def test_only_guests_past_the_cutoff_are_deleted(self, seeded_db, settings):
        store = UserStore(seeded_db, settings)
        old = await store.mint_guest()
        fresh = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", old.id),
        )

        deleted = await store.delete_expired_guests("2021-01-01T00:00:00+00:00")

        assert deleted == 1
        assert await store.get(old.id) is None
        assert await store.get(fresh.id) is not None

    async def test_a_signed_in_user_never_expires(self, seeded_db, settings):
        store = UserStore(seeded_db, settings)
        user = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET kind = 'user', last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user.id),
        )

        deleted = await store.delete_expired_guests("2021-01-01T00:00:00+00:00")

        assert deleted == 0
        assert await store.get(user.id) is not None

    async def test_deleting_a_guest_cascades_to_its_rows(self, seeded_db, settings):
        """The foreign keys are what make expiry one DELETE instead of six."""
        store = UserStore(seeded_db, settings)
        user = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user.id),
        )

        await store.delete_expired_guests("2021-01-01T00:00:00+00:00")

        rows = await seeded_db.fetch_all(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (user.id,)
        )
        assert rows == []


class TestActiveUsers:
    async def test_only_users_seen_since_the_cutoff_are_listed(self, seeded_db, settings):
        store = UserStore(seeded_db, settings)
        recent = await store.mint_guest()
        old = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", old.id),
        )

        active = await store.list_active_since("2021-01-01T00:00:00+00:00")

        assert recent.id in active
        assert old.id not in active
