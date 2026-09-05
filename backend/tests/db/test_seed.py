"""Tests for default seed data."""

from __future__ import annotations

import pytest

from app.clock import iso_seconds_ago, utcnow_iso
from app.config import Settings
from app.db import DEFAULT_WATCHLIST, Database, seed_user
from app.db.seed import _DEMO_BACKFILL_SECONDS
from tests.conftest import create_seeded_user


class TestSeedUser:
    async def test_seeds_a_fresh_user(self, db: Database, settings: Settings):
        """A newly created user gets their starting cash and watchlist."""
        await create_seeded_user(db, settings, "alice")

        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'alice'")
        assert profile["cash_balance"] == 10_000.0

        rows = await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = 'alice'")
        assert {row["ticker"] for row in rows} == set(DEFAULT_WATCHLIST)

    async def test_seeds_every_user_not_just_the_first(self, db: Database, settings: Settings):
        """The single-user form asked "is the database empty?", which is false
        the moment one user exists -- so it would have seeded nobody after."""
        await create_seeded_user(db, settings, "alice")
        await create_seeded_user(db, settings, "bob")

        for user_id in ("alice", "bob"):
            rows = await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = ?", (user_id,))
            assert len(rows) == len(DEFAULT_WATCHLIST)

    async def test_reseeding_leaves_an_edited_watchlist_alone(
        self, db: Database, settings: Settings
    ):
        """Seeding is idempotent: it restores what is missing, duplicates nothing."""
        await create_seeded_user(db, settings, "alice")
        await db.execute("DELETE FROM watchlist WHERE user_id = 'alice' AND ticker = 'AAPL'")

        await seed_user(db, settings, "alice")

        rows = await db.fetch_all("SELECT ticker FROM watchlist WHERE user_id = 'alice'")
        assert len(rows) == len(DEFAULT_WATCHLIST)
        assert len({row["ticker"] for row in rows}) == len(DEFAULT_WATCHLIST)

        # The t=0 snapshot is guarded too. Unguarded, a repair pass would put
        # a second `initial_cash` point, dated today, into a chart that has
        # long since moved off that value.
        snapshots = await db.fetch_all(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = 'alice'"
        )
        assert len(snapshots) == 1

    async def test_seeds_canonical_tickers(self, db: Database, settings: Settings):
        """Seeded tickers go through the same canonicalization as user input."""
        await create_seeded_user(db, settings, "alice")
        rows = await db.fetch_all("SELECT ticker FROM watchlist")
        assert all(row["ticker"] == row["ticker"].strip().upper() for row in rows)

    async def test_respects_configured_initial_cash(self, db: Database):
        """The starting balance comes from settings, not a hardcoded constant."""
        custom = Settings(initial_cash=250.0)
        await create_seeded_user(db, custom, "alice")
        profile = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = 'alice'")
        assert profile["cash_balance"] == 250.0


@pytest.mark.asyncio
async def test_demo_seed_writes_holdings_trades_and_a_value_curve(db, settings):
    """A guest opens on a portfolio worth looking at, not on an empty one."""
    await db.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at, kind, last_seen_at) "
        "VALUES (?, ?, ?, 'guest', ?)",
        ("demo_user", settings.initial_cash, utcnow_iso(), utcnow_iso()),
    )
    await seed_user(db, settings, "demo_user", demo=True)

    positions = await db.fetch_all(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
        ("demo_user",),
    )
    assert [(r["ticker"], float(r["quantity"]), float(r["avg_cost"])) for r in positions] == [
        ("AAPL", 10.0, 186.40),
        ("MSFT", 4.0, 428.00),
        ("NVDA", 2.0, 781.50),
        ("TSLA", 3.0, 254.00),
    ]

    # Cash is reduced by the cost basis, so the numbers add up to a story a
    # user could have lived: they started with 10,000 and bought these.
    cash = await db.fetch_one("SELECT cash_balance FROM users_profile WHERE id = ?", ("demo_user",))
    assert float(cash["cash_balance"]) == 4099.00

    trades = await db.fetch_all(
        "SELECT ticker, side, is_demo, executed_at FROM trades WHERE user_id = ? "
        "ORDER BY executed_at",
        ("demo_user",),
    )
    assert len(trades) == 4
    assert all(t["side"] == "buy" and t["is_demo"] for t in trades)

    # Staggered across the backfill window, not bunched at "just now" -- the
    # whole reason the backing trades exist is to give the History view a
    # plausible spread on first load.
    executed_at = [t["executed_at"] for t in trades]
    assert len(set(executed_at)) == 4
    assert executed_at == sorted(executed_at)
    now_iso = utcnow_iso()
    oldest_cutoff = iso_seconds_ago(_DEMO_BACKFILL_SECONDS)
    assert oldest_cutoff < executed_at[0] < now_iso
    # The oldest trade is comfortably inside the window, not right at "now".
    assert executed_at[0] < iso_seconds_ago(_DEMO_BACKFILL_SECONDS // 10)

    # More than the single t=0 point, so the Performance chart opens on a
    # curve rather than on "charting starts once two snapshots land".
    snapshots = await db.fetch_all(
        "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?", ("demo_user",)
    )
    assert len(snapshots) > 2
    assert all(5_000 < float(s["total_value"]) < 20_000 for s in snapshots)


@pytest.mark.asyncio
async def test_seed_without_demo_is_cash_only(db, settings):
    """The old behaviour is still reachable, and is what DEMO_PORTFOLIO=false gets."""
    await db.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at, kind, last_seen_at) "
        "VALUES (?, ?, ?, 'guest', ?)",
        ("plain_user", settings.initial_cash, utcnow_iso(), utcnow_iso()),
    )
    await seed_user(db, settings, "plain_user")

    positions = await db.fetch_all(
        "SELECT ticker FROM positions WHERE user_id = ?", ("plain_user",)
    )
    trades = await db.fetch_all("SELECT id FROM trades WHERE user_id = ?", ("plain_user",))
    assert positions == [] and trades == []
