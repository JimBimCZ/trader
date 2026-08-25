"""Attaching a provider identity to a row, and asking whether it has been used."""

from __future__ import annotations

import pytest

from app.identity import UserStore


@pytest.fixture
def store(db, settings) -> UserStore:
    return UserStore(db, settings)


@pytest.mark.asyncio
class TestLookup:
    async def test_an_unknown_identity_is_none(self, store):
        assert await store.lookup_identity("google", "nobody") is None

    async def test_a_linked_identity_returns_its_user(self, store):
        user = await store.mint_guest()
        await store.attach_identity(user.id, "google", "sub-1", "a@b.c")
        assert await store.lookup_identity("google", "sub-1") == user.id

    async def test_the_same_subject_at_another_provider_is_a_different_identity(self, store):
        """D-6 in the schema: the key is the pair, never the email or the
        subject alone. GitHub's user 12345 is not Google's user 12345."""
        user = await store.mint_guest()
        await store.attach_identity(user.id, "google", "12345", None)
        assert await store.lookup_identity("github", "12345") is None


@pytest.mark.asyncio
class TestPromote:
    async def test_promotion_is_in_place(self, store):
        """The row keeps its id, so the cookie already in the browser stays
        valid and every row that points at it follows the user across."""
        guest = await store.mint_guest()
        promoted = await store.promote(guest.id, "a@b.c", "Ada", "https://img/x.png")
        assert promoted.id == guest.id
        assert promoted.kind == "user"
        assert (promoted.email, promoted.display_name, promoted.avatar_url) == (
            "a@b.c",
            "Ada",
            "https://img/x.png",
        )

    async def test_promotion_keeps_the_portfolio(self, store, db):
        guest = await store.mint_guest()
        await db.execute("UPDATE users_profile SET cash_balance = 4242.0 WHERE id = ?", (guest.id,))
        promoted = await store.promote(guest.id, None, None, None)
        assert promoted.cash_balance == 4242.0


@pytest.mark.asyncio
class TestHasActivity:
    async def test_a_freshly_minted_guest_has_none(self, store):
        """The common case, and the one that must never produce a prompt: an
        untouched guest signing in has nothing to lose."""
        guest = await store.mint_guest()
        assert await store.has_activity(guest.id) is False

    async def test_a_trade_is_activity(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES ('t1', ?, 'AAPL', 'buy', 1, 190.0, '2026-01-01T00:00:00Z')",
            (guest.id,),
        )
        assert await store.has_activity(guest.id) is True

    async def test_a_chat_message_is_activity(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES ('c1', ?, 'user', 'hi', NULL, '2026-01-01T00:00:00Z')",
            (guest.id,),
        )
        assert await store.has_activity(guest.id) is True

    async def test_removing_a_seeded_ticker_is_activity(self, store, db):
        """Activity is a change away from the seed, in either direction --
        counting only additions would discard a curated watchlist silently."""
        guest = await store.mint_guest()
        await db.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = 'NFLX'", (guest.id,))
        assert await store.has_activity(guest.id) is True

    async def test_adding_a_ticker_is_activity(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) "
            "VALUES ('w1', ?, 'PYPL', '2026-01-01T00:00:00Z')",
            (guest.id,),
        )
        assert await store.has_activity(guest.id) is True
