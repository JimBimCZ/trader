"""Default seed data, written once per user."""

from __future__ import annotations

import logging
import uuid

from ..clock import iso_seconds_ago, now_ts, utcnow_iso
from ..config import Settings
from ..market.deterministic import price_at
from ..market.tickers import canonicalize_ticker
from ..portfolio.formulas import round_cash
from ..portfolio.repository import TradeRepository
from .connection import Database

logger = logging.getLogger(__name__)

#: The ten tickers a fresh install starts watching.
DEFAULT_WATCHLIST = [
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
]

#: The demo portfolio a guest opens on: four holdings, deliberately two in
#: profit and two at a loss against their seed prices, so the heatmap has both
#: colours to draw and the positions table shows a signed value in each
#: direction. Every ticker is already in DEFAULT_WATCHLIST, so the tracked
#: ticker union is unchanged by seeding one of these.
#: (ticker, quantity, avg_cost)
DEMO_HOLDINGS: list[tuple[str, float, float]] = [
    ("AAPL", 10.0, 186.40),
    ("MSFT", 4.0, 428.00),
    ("NVDA", 2.0, 781.50),
    ("TSLA", 3.0, 254.00),
]

#: How far back the demo's value curve reaches, and how many points it holds.
#: Six hours at nine-minute spacing: enough shape to read as a session, few
#: enough rows that seeding stays one round trip per point on a cold Neon.
_DEMO_BACKFILL_SECONDS = 6 * 3600
_DEMO_BACKFILL_POINTS = 40


async def seed_user(db: Database, settings: Settings, user_id: str, *, demo: bool = False) -> None:
    """Give one user the default watchlist and a snapshot at t=0.

    The profile row must already exist -- the watchlist rows carry a foreign
    key to it, and it is where the starting cash balance is written. Callers
    create the row and seed inside one transaction.

    Per user, not per database. The single-user form of this asked "is the
    database empty?", which with many users is false the moment the first
    guest exists -- so it would have silently skipped seeding everyone after
    them.

    The snapshot is what stops a brand-new user's P&L chart from being empty
    until the writer's next tick. Startup used to leave one behind for the
    single seeded user; with users minted on demand it belongs here, where
    both minting and reset go through it.

    `demo=True` seeds the four `DEMO_HOLDINGS`, their backing trades, and a
    backfilled value curve, instead of the single t=0 snapshot.
    """
    now = utcnow_iso()
    for ticker in DEFAULT_WATCHLIST:
        await db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, ticker) DO NOTHING",
            (str(uuid.uuid4()), user_id, canonicalize_ticker(ticker), now),
        )

    if demo:
        await _seed_demo_portfolio(db, settings, user_id, now)
        return

    # Guarded the way the watchlist inserts are, so the whole function is
    # idempotent: a re-seed that repaired missing rows would otherwise inject
    # a second `initial_cash` point, dated today, into a chart that has moved
    # on since. Reset deletes this user's snapshots inside the same
    # transaction, so it still gets its fresh t=0 point.
    await db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "SELECT ?, ?, ?, ? "
        "WHERE NOT EXISTS (SELECT 1 FROM portfolio_snapshots WHERE user_id = ?)",
        (str(uuid.uuid4()), user_id, settings.initial_cash, now, user_id),
    )
    logger.info("Seeded %d watchlist tickers for %s", len(DEFAULT_WATCHLIST), user_id)


async def _seed_demo_portfolio(db: Database, settings: Settings, user_id: str, now: str) -> None:
    """Give one user the demo holdings, their backing trades, and a value curve.

    Guarded the way the watchlist inserts are, so a re-seed repairs rather
    than duplicates: a second pass would otherwise inject a second set of
    positions and a second value curve into a chart that has moved on.

    The trades are real rows carrying `is_demo`, not decoration. PLAN.md's
    D-21 makes `trades` authoritative and positions a projection of it, so a
    position with nothing behind it would be the one shape the invariant
    forbids -- and the History view would open empty, which is the same
    complaint this whole change exists to answer.
    """
    existing = await db.fetch_one(
        "SELECT 1 AS present FROM positions WHERE user_id = ? LIMIT 1", (user_id,)
    )
    if existing is not None:
        return

    basis = 0.0
    for ticker, quantity, avg_cost in DEMO_HOLDINGS:
        canonical = canonicalize_ticker(ticker)
        basis += quantity * avg_cost
        await db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, ticker) DO NOTHING",
            (str(uuid.uuid4()), user_id, canonical, quantity, avg_cost, now),
        )
        await TradeRepository(db, user_id).insert(
            canonical, "buy", quantity, avg_cost, is_demo=True
        )

    cash = round_cash(settings.initial_cash - basis)
    await db.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, user_id))

    # Valued from `price_at`, a pure function of the clock, so on the
    # serverless deployment -- where it is also the live price source -- the
    # backfilled curve joins the live one seamlessly.
    #
    # ponytail: on the container target the live source is the stateful GBM
    # simulator, whose path is generated in-process and will not match. Both
    # start from the same SEED_PRICES, so the curve lands in the right place
    # and the join is invisible at chart scale. Upgrade path if it ever
    # matters: have the simulator expose a price_at-shaped backfill of its own.
    # `iso_seconds_ago` rather than a local formatter: `last_seen_at` and every
    # other stored timestamp go through it, and a second spelling of the same
    # format is exactly what its docstring warns breaks string comparison.
    now_seconds = now_ts()
    step = _DEMO_BACKFILL_SECONDS / _DEMO_BACKFILL_POINTS
    seed = settings.sim_seed or 0
    vol_multiplier = settings.sim_vol_multiplier

    # Batched into one multi-row INSERT rather than 40 sequential db.execute
    # calls: this runs inside mint_guest's transaction, and on a cold Neon
    # connection at 50-100ms per round trip a per-row loop would add
    # 2.4-4.8s to the first request a visitor makes -- the exact latency the
    # rest of this plan exists to remove. The Database wrapper has no
    # executemany, so a joined VALUES list with a flat parameter tuple is the
    # way; 40 rows * 4 params = 160 placeholders, well under Postgres's limit.
    rows = []
    params: list[object] = []
    for index in range(_DEMO_BACKFILL_POINTS):
        ago = int(_DEMO_BACKFILL_SECONDS - index * step)
        at = now_seconds - ago
        value = cash + sum(
            quantity * price_at(canonicalize_ticker(ticker), at, seed, vol_multiplier)
            for ticker, quantity, _ in DEMO_HOLDINGS
        )
        rows.append("(?, ?, ?, ?)")
        params.extend((str(uuid.uuid4()), user_id, round_cash(value), iso_seconds_ago(ago)))

    await db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES " + ", ".join(rows),
        tuple(params),
    )

    logger.info("Seeded the demo portfolio for %s", user_id)
