# Demo Onboarding and Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the first load racing itself into empty charts, give a signed-out visitor a portfolio worth looking at, and split the workspace into three real routes so the portfolio has room.

**Architecture:** The boot sequence resolves the session before fanning out, so one guest is minted instead of four. A guest is seeded with four holdings, four `is_demo` trades and a backfilled snapshot curve; signing in clears that seed only when the guest has done nothing of their own. The single workspace page becomes three routes inside a Next.js route group whose shared layout keeps one SSE connection alive across navigation.

**Tech Stack:** FastAPI + asyncpg (Postgres), pytest / pytest-asyncio; Next.js 15 App Router static export, TypeScript, Zustand, Tailwind, Vitest + React Testing Library; Playwright for E2E.

**Spec:** `docs/superpowers/specs/2026-09-05-demo-onboarding-and-navigation-design.md`

## Global Constraints

- **Branch:** `feat/demo-onboarding-and-navigation`, already created, spec already committed on it.
- **Backend tests need Postgres.** `TEST_DATABASE_URL` defaults to `postgresql://trader:trader@localhost:5432/trader`. Each test gets a throwaway schema via the `db_schema` fixture. Run from `backend/`: `uv run pytest`.
- **Frontend tests:** run from `frontend/`: `npm test -- --run`. Watch mode is `npm test`.
- **Migrations are append-only and idempotent.** Never edit a deployed statement in `MIGRATIONS`; append a new one. There is no version table — every statement must be safe to re-run on every startup.
- **`?` is the placeholder** in every SQL string; the Postgres adapter rewrites it. Do not write `$1`.
- **Money is 2dp, quantity 6dp**, via `round_cash` / `round_quantity` in `app/portfolio/formulas.py`. Never round by hand.
- **Colour literals live only in `frontend/lib/theme.ts`.** Components use Tailwind tokens (`text-text-muted`, `bg-surface-sunk`, `border-border`). Any new foreground/background pairing used for small text must clear 4.5:1 in both appearances and be asserted in `__tests__/lib/theme.test.ts`.
- **Colour is never the only encoding.** Every coloured number carries a sign and an arrow glyph — use the existing `SignedValue` / `ChangeBadge` components and `directionGlyph` from `lib/format.ts`.
- **Corner radii:** 10px controls, 14px cards, 20px chrome — via the `rounded-control` / `card` / `material` classes, not raw pixel values.
- **Demo holdings, exact values** (spec §4): AAPL 10 @ 186.40, MSFT 4 @ 428.00, NVDA 2 @ 781.50, TSLA 3 @ 254.00. Cost basis 5,901.00. Cash after seeding 4,099.00.
- **Commit messages:** imperative, describing the behaviour change rather than the file list, and ending with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
  ```

---

## File Structure

**Backend — modified**
- `app/config.py` — `demo_portfolio: bool` setting
- `app/db/migrations.py` — migration 004, the `is_demo` column
- `app/db/seed.py` — `demo=` parameter, demo holdings, backing trades, snapshot backfill
- `app/db/__init__.py` — re-export whatever `seed.py` newly exports
- `app/identity/store.py` — `mint_guest` passes the flag; `has_activity` excludes demo trades
- `app/auth/router.py` — clear the demo on a qualifying sign-in
- `app/system/service.py` — `ResetService` reads the user's kind and re-seeds accordingly
- `app/portfolio/formulas.py` — `replay_realized`
- `app/portfolio/repository.py` — `TradeRepository.list_all`
- `app/portfolio/service.py` — `get_trades`
- `app/portfolio/router.py` — `GET /api/portfolio/trades`

**Backend — tests**
- `tests/portfolio/test_formulas.py` — `replay_realized` (file exists; append)
- `tests/db/test_seed.py` — demo seed shape (file exists; append)
- `tests/identity/test_store.py` — `has_activity` with demo trades (file exists; append)
- `tests/auth/test_demo_clearing.py` — **new**, the sign-in rules
- `tests/portfolio/test_trades_route.py` — **new**, the endpoint
- `tests/test_api.py` — `TestExportedSubroutes` gains the two new routes

**Frontend — created**
- `app/(workspace)/layout.tsx` — the persistent shell
- `app/(workspace)/page.tsx` — Overview (moved from `app/page.tsx`)
- `app/(workspace)/portfolio/page.tsx` — Portfolio
- `app/(workspace)/history/page.tsx` — History
- `components/portfolio/TradeHistoryTable.tsx`
- `components/onboarding/Tour.tsx`
- `components/onboarding/steps.ts` — the step list, so the component holds no copy

**Frontend — modified**
- `lib/useAppBoot.ts` — session first, then fan out
- `lib/types.ts` — `TradeRecord`
- `lib/api/endpoints.ts` — `fetchTrades`
- `store/usePortfolioStore.ts` — `trades`, `tradesStatus`, `refreshTrades`
- `components/layout/Rail.tsx` — `next/link` navigation
- `components/layout/panels.ts` — re-keyed to the surviving overview panels
- `app/page.tsx` — deleted (moves into the route group)

---

### Task 1: Resolve the session before the boot fan-out

Independent of every other task and shippable alone. This is the fix for the empty charts.

**Files:**
- Modify: `frontend/lib/useAppBoot.ts`
- Test: `frontend/__tests__/lib/useAppBoot.test.tsx`

**Interfaces:**
- Consumes: nothing
- Produces: no signature change. `useAppBoot(): boolean` is unchanged; only the call order inside it moves.

- [ ] **Step 1: Write the failing test**

Append to `frontend/__tests__/lib/useAppBoot.test.tsx`. The existing `beforeEach` already replaces all four store actions with deferreds; add an order log alongside them.

```tsx
it("resolves the session before fetching anything else", async () => {
  const calls: string[] = [];
  useSessionStore.setState({
    load: () => {
      calls.push("session");
      return session.promise;
    },
  });
  usePortfolioStore.setState({
    refresh: () => {
      calls.push("portfolio");
      return portfolio.promise;
    },
  });
  useWatchlistStore.setState({
    refresh: () => {
      calls.push("watchlist");
      return watchlist.promise;
    },
  });
  useChatStore.setState({
    refresh: () => {
      calls.push("chat");
      return chat.promise;
    },
  });

  renderHook(() => useAppBoot());

  // Only the session has been asked for: the other three would each mint
  // their own guest if they went out without the cookie it brings back.
  await act(async () => {});
  expect(calls).toEqual(["session"]);

  await act(async () => {
    session.resolve();
  });
  expect(calls.slice(1).sort()).toEqual(["chat", "portfolio", "watchlist"]);
});

it("still fetches the rest when the session call fails", async () => {
  const { result } = renderHook(() => useAppBoot());

  await act(async () => {
    session.reject(new Error("cold start"));
  });
  await settleAll(() => {
    portfolio.resolve();
    watchlist.resolve();
    chat.resolve();
  });

  expect(result.current).toBe(true);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd frontend && npm test -- --run __tests__/lib/useAppBoot.test.tsx
```

Expected: FAIL — `calls` is `["session", "portfolio", "watchlist", "chat"]` on the first assertion, because all four fire together today.

- [ ] **Step 3: Change the call order**

In `frontend/lib/useAppBoot.ts`, replace the `Promise.race` body's first argument. The current code is:

```ts
    void Promise.race([
      Promise.allSettled([loadSession(), refreshPortfolio(), refreshWatchlist(), refreshChat()]),
```

Replace with a small async function, and add the explanatory comment — this file documents its reasoning throughout and a bare reorder would read as arbitrary:

```ts
    // Sequential on purpose, and the ordering is the whole point.
    //
    // A first-time visitor arrives with no session cookie, and EVERY
    // user-resolving route mints a guest when it finds none: twelve inserts
    // and a full reconcile, on a serverless instance that pays its own cold
    // start. Fired together, these four requests minted four guests, kept
    // three of them orphaned, and took 4-10s each where a single cookied
    // request takes 700ms -- long enough on a cold instance that the client's
    // own 20s deadline aborted them. An aborted watchlist is a chart with no
    // ticker to draw; an aborted history is a Performance panel showing its
    // load-failure state. That is what "the charts sometimes don't load" was.
    //
    // Resolving the session first mints exactly one guest and hands the other
    // three the cookie, so they are cheap reads rather than three more mints.
    const bootCalls = async () => {
      // Swallowed rather than awaited bare: a session that fails must not
      // skip the other three. `loadSession` records its own failure on the
      // store, which is what the account control renders.
      await loadSession().catch(() => {});
      await Promise.allSettled([refreshPortfolio(), refreshWatchlist(), refreshChat()]);
    };

    void Promise.race([
      bootCalls(),
```

Leave the rest of the effect — the `BOOT_MAX_MS` cap promise, the `BOOT_MIN_MS` hold, the teardown — exactly as it is.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd frontend && npm test -- --run __tests__/lib/useAppBoot.test.tsx
```

Expected: PASS, including the four pre-existing tests in the file.

- [ ] **Step 5: Update the docstring**

The `useAppBoot` docstring says "The four calls here". Amend that paragraph to name the two stages:

```
 * The session goes first and alone; the other three follow together once it
 * has answered. See the comment in the effect for why that ordering is load-
 * bearing rather than stylistic.
```

- [ ] **Step 6: Run the full frontend suite**

```bash
cd frontend && npm test -- --run
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/useAppBoot.ts frontend/__tests__/lib/useAppBoot.test.tsx
git commit -m "$(cat <<'EOF'
Mint one guest on a first visit, not four

The four boot calls all resolve the caller, and a first visit carries no
cookie, so each of them minted its own guest -- twelve inserts and a
reconcile apiece, on four separate cold instances. Measured against the
live deployment: 4-10s each concurrently against 700ms with a cookie,
and on a genuinely cold instance four of the five aborted at the
client's own 20s deadline. The aborted ones were the watchlist and the
value history, which is why the charts were the part that looked broken.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 2: `is_demo` on trades, excluded from `has_activity`

**Files:**
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/schema.py` (the `trades` CREATE TABLE, for fresh databases)
- Modify: `backend/app/identity/store.py:160-192` (`has_activity`)
- Modify: `backend/app/portfolio/repository.py:95-119` (`TradeRepository.insert`)
- Test: `backend/tests/identity/test_store.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `TradeRepository.insert(ticker, side, quantity, price, *, is_demo: bool = False) -> Trade`
  - The `trades.is_demo` column, `BOOLEAN NOT NULL DEFAULT FALSE`
  - `has_activity(user_id)` now ignores rows where `is_demo` is true

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/identity/test_store.py`. Match the file's existing fixture usage (`db`, `settings`).

```python
@pytest.mark.asyncio
async def test_has_activity_ignores_demo_trades(db, settings):
    """A seeded demo must not make every guest look like it has done something.

    has_activity gates the sign-in conflict dialog. If the demo counted, the
    dialog would fire on every single sign-in -- which trains people to
    dismiss the one warning that matters -- and the demo could never be
    cleared, because clearing is conditioned on this being false.
    """
    store = UserStore(db, settings)
    user = await store.mint_guest()

    await TradeRepository(db, user.id).insert("AAPL", "buy", 10, 186.40, is_demo=True)
    assert await store.has_activity(user.id) is False

    await TradeRepository(db, user.id).insert("AAPL", "buy", 1, 190.00)
    assert await store.has_activity(user.id) is True
```

Add the import at the top of the file if it is not already there:

```python
from app.portfolio.repository import TradeRepository
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && uv run pytest tests/identity/test_store.py::test_has_activity_ignores_demo_trades -v
```

Expected: FAIL with `TypeError: insert() got an unexpected keyword argument 'is_demo'`.

- [ ] **Step 3: Add the column to the fresh-database schema**

In `backend/app/db/schema.py`, find the `CREATE TABLE IF NOT EXISTS trades` statement and add the column after `executed_at`:

```sql
        is_demo     BOOLEAN NOT NULL DEFAULT FALSE,
```

- [ ] **Step 4: Append migration 004**

At the end of the `MIGRATIONS` list in `backend/app/db/migrations.py`, before the closing `]`:

```python
    # 004 -- demo trades are excluded from has_activity(), which gates both
    # the sign-in conflict dialog and whether a demo portfolio may be
    # cleared. Without the flag every seeded guest counts as active: the
    # dialog fires on every sign-in, and the demo it exists to clear never
    # clears. schema.py carries the column too, for a database created fresh.
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE",
```

- [ ] **Step 5: Take the flag on insert**

In `backend/app/portfolio/repository.py`, change `TradeRepository.insert` to accept and write it. Keyword-only, so no existing positional call site can pass it by accident:

```python
    async def insert(
        self,
        ticker: str,
        side: Side,
        quantity: float,
        price: float,
        *,
        is_demo: bool = False,
    ) -> Trade:
        """Append one fill.

        `is_demo` marks a row the seeder wrote rather than the user. It is
        deliberately absent from `Trade`: nothing above this repository needs
        to tell them apart, and the History view shows both, because a demo
        trade honestly describes how a demo position came to be.
        """
```

Add `is_demo` to the INSERT's column list, its placeholder list, and the parameter tuple after `trade.executed_at`.

- [ ] **Step 6: Exclude demo trades from `has_activity`**

In `backend/app/identity/store.py`, change the trades subquery inside `has_activity`:

```sql
                (SELECT COUNT(*) FROM trades WHERE user_id = ? AND NOT is_demo) AS trades,
```

Add a paragraph to the docstring, after the existing "Three signals" one:

```
        Demo trades do not count. A seeded guest has four of them, and if
        they registered here every guest would look active: the conflict
        dialog would fire on every sign-in, and the demo would never meet the
        "no activity of their own" condition that lets it be cleared.
```

- [ ] **Step 7: Run the test to verify it passes**

```bash
cd backend && uv run pytest tests/identity/test_store.py -v
```

Expected: PASS.

- [ ] **Step 8: Run the full backend suite**

```bash
cd backend && uv run pytest -q
```

Expected: PASS. The migration is additive with a default, so nothing else should move.

- [ ] **Step 9: Commit**

```bash
git add backend/app/db/migrations.py backend/app/db/schema.py \
        backend/app/identity/store.py backend/app/portfolio/repository.py \
        backend/tests/identity/test_store.py
git commit -m "$(cat <<'EOF'
Tell a seeded trade apart from one the user made

has_activity gates the sign-in conflict dialog and, shortly, whether a
demo portfolio may be cleared. A demo seeded as trades would make every
guest look active on both counts: a warning that fires every time is a
warning nobody reads, and a demo that always looks touched never gets
cleared away.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 3: Seed the demo portfolio

**Files:**
- Modify: `backend/app/config.py` (add `demo_portfolio`)
- Modify: `backend/app/db/seed.py`
- Modify: `backend/app/db/__init__.py` (export `DEMO_HOLDINGS`)
- Modify: `backend/app/identity/store.py` (`mint_guest`)
- Modify: `backend/app/system/service.py` (`ResetService.reset`)
- Test: `backend/tests/db/test_seed.py`

**Interfaces:**
- Consumes: `TradeRepository.insert(..., is_demo=True)` from Task 2
- Produces:
  - `Settings.demo_portfolio: bool` (default `True`, env `DEMO_PORTFOLIO`)
  - `app.db.seed.DEMO_HOLDINGS: list[tuple[str, float, float]]` — `(ticker, quantity, avg_cost)`
  - `seed_user(db, settings, user_id, *, demo: bool = False) -> None`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/db/test_seed.py`:

```python
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
    cash = await db.fetch_one(
        "SELECT cash_balance FROM users_profile WHERE id = ?", ("demo_user",)
    )
    assert float(cash["cash_balance"]) == 4099.00

    trades = await db.fetch_all(
        "SELECT ticker, side, is_demo FROM trades WHERE user_id = ?", ("demo_user",)
    )
    assert len(trades) == 4
    assert all(t["side"] == "buy" and t["is_demo"] for t in trades)

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
```

Ensure the file imports `utcnow_iso` from `app.clock` and `seed_user` from `app.db`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/db/test_seed.py -v
```

Expected: FAIL with `TypeError: seed_user() got an unexpected keyword argument 'demo'`.

- [ ] **Step 3: Add the setting**

In `backend/app/config.py`, add a field to the `Settings` dataclass next to `initial_cash`:

```python
    #: Whether a freshly minted guest is seeded with the demo portfolio of
    #: `app.db.seed.DEMO_HOLDINGS` rather than cash alone. False restores the
    #: pre-demo behaviour exactly, which is what the E2E fresh-start
    #: assertions are written against.
    demo_portfolio: bool = True
```

In `from_env`, add to the `cls(...)` call:

```python
            demo_portfolio=_env_bool("DEMO_PORTFOLIO", True),
```

- [ ] **Step 4: Write the demo seed**

In `backend/app/db/seed.py`, add the holdings table and the seeding branch. Full new content for the additions:

```python
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
```

Then, inside `seed_user`, after the existing watchlist loop and before the t=0 snapshot insert:

```python
    if demo:
        await _seed_demo_portfolio(db, settings, user_id, now)
        return
```

And the helper, below `seed_user`:

```python
async def _seed_demo_portfolio(
    db: Database, settings: Settings, user_id: str, now: str
) -> None:
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
    await db.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, user_id)
    )

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
    for index in range(_DEMO_BACKFILL_POINTS):
        ago = int(_DEMO_BACKFILL_SECONDS - index * step)
        at = now_seconds - ago
        value = cash + sum(
            quantity * price_at(canonicalize_ticker(ticker), at)
            for ticker, quantity, _ in DEMO_HOLDINGS
        )
        await db.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, round_cash(value), iso_seconds_ago(ago)),
        )

    logger.info("Seeded the demo portfolio for %s", user_id)
```

Add the imports at the top of `seed.py`:

```python
from ..clock import iso_seconds_ago, now_ts, utcnow_iso
from ..market.deterministic import price_at
from ..portfolio.formulas import round_cash
from ..portfolio.repository import TradeRepository
```

`price_at(ticker, timestamp, seed=0, vol_multiplier=1.0)` — check the signature in `app/market/deterministic.py` and pass `settings.sim_seed or 0` and `settings.sim_vol_multiplier` if it takes them, so the backfill matches the live series on a deployment that has tuned either.

Change the signature and docstring of `seed_user`:

```python
async def seed_user(
    db: Database, settings: Settings, user_id: str, *, demo: bool = False
) -> None:
```

Note in the docstring that `demo=True` seeds holdings, backing trades and a backfilled value curve instead of the single t=0 snapshot.

- [ ] **Step 5: Run the seed tests to verify they pass**

```bash
cd backend && uv run pytest tests/db/test_seed.py -v
```

Expected: PASS.

- [ ] **Step 6: Wire the flag into minting**

In `backend/app/identity/store.py`, `mint_guest`:

```python
            await seed_user(
                self._db, self._settings, user_id, demo=self._settings.demo_portfolio
            )
```

The returned `User` carries `cash_balance=self._settings.initial_cash`, which is now wrong for a demo guest. Re-read the row instead of constructing it — the transaction has committed by then:

```python
        logger.info("Minted guest %s", user_id)
        # Re-read rather than construct: the demo seed moves cash_balance, and
        # returning the pre-seed figure would put a stale number in front of
        # the caller that resolves this user.
        minted = await self.get(user_id)
        if minted is None:  # pragma: no cover -- just committed
            raise LookupError(f"Minted a guest that does not exist: {user_id}")
        return minted
```

- [ ] **Step 7: Wire the flag into reset**

In `backend/app/system/service.py`, `ResetService.reset`, inside the transaction and before the `seed_user` call:

```python
                # A guest's reset restores the demo, because the demo IS
                # their seeded starting state. A signed-in account's reset
                # returns them to a clean initial_cash -- once the account is
                # real, "reset" should not hand back a portfolio they never
                # placed.
                kind_row = await self._db.fetch_one(
                    "SELECT kind FROM users_profile WHERE id = ?", (self._user_id,)
                )
                demo = (
                    self._settings.demo_portfolio
                    and kind_row is not None
                    and kind_row["kind"] == "guest"
                )
                await self._db.execute(
                    "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                    (self._settings.initial_cash, self._user_id),
                )
                await seed_user(self._db, self._settings, self._user_id, demo=demo)
```

Replace the existing `UPDATE ... cash_balance` + `seed_user` pair with the block above; the cash update must stay *before* `seed_user`, because the demo seed subtracts the cost basis from it.

- [ ] **Step 8: Export the holdings**

In `backend/app/db/__init__.py`, add `DEMO_HOLDINGS` to the `seed` import and to `__all__`, beside `DEFAULT_WATCHLIST`.

- [ ] **Step 9: Run the full backend suite**

```bash
cd backend && uv run pytest -q
```

Expected: some pre-existing tests that assert a fresh guest has `cash_balance == 10000` or no positions will now fail. Fix each by constructing its `Settings` with `demo_portfolio=False` — those tests are about the seeding baseline, not about the demo. Do **not** weaken an assertion to accommodate the demo.

- [ ] **Step 10: Commit**

```bash
git add backend/app/config.py backend/app/db/ backend/app/identity/store.py \
        backend/app/system/service.py backend/tests/
git commit -m "$(cat <<'EOF'
Open on a portfolio worth looking at

A signed-out visitor arrived at $10,000 in cash, no positions and one
snapshot: a heatmap with nothing to draw and a Performance panel saying
charting starts in a minute. A guest is now seeded with four holdings --
two up, two down, so both colours are on screen -- their backing trades,
and six hours of value curve computed from the deterministic price
model.

DEMO_PORTFOLIO=false restores the old behaviour exactly, which is what
the E2E fresh-start assertions run against.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 4: Clear the demo when a guest signs in

The dangerous task. Read spec §5 before starting.

**Files:**
- Modify: `backend/app/auth/router.py:199-236` (`oauth_callback`)
- Create: `backend/tests/auth/test_demo_clearing.py`

**Interfaces:**
- Consumes: `Settings.demo_portfolio`, `seed_user(..., demo=False)` from Task 3; `has_activity` from Task 2
- Produces: `app.auth.router._clear_demo_if_untouched(request, user_id, was_guest) -> None`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/auth/test_demo_clearing.py`. It reuses `tests/auth/test_auth_routes.py`'s `auth_client` fixture shape: `_complete_exchange` is stubbed at the seam so the decision, the store writes and the cookie are all the real code path, and the `?sub=` query parameter chooses the provider identity.

```python
"""What signing in does to a seeded demo portfolio.

The rule has two conditions and both are load-bearing (design doc §5).
`test_a_second_provider_on_an_existing_account_keeps_everything` is the one
that matters most: without the guest check, connecting GitHub to an account
that already signed in with Google would delete a real portfolio.
"""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.auth.providers import OAuthProfile
from app.main import create_app
from tests.conftest import CLIENT_BASE_URL, _drop_schema


@pytest.fixture
def demo_settings(settings):
    """OAuth configured, and the demo portfolio on — which is the default."""
    return dataclasses.replace(
        settings,
        google_client_id="id",
        google_client_secret="secret",
        github_client_id="gh-id",
        github_client_secret="gh-secret",
        demo_portfolio=True,
    )


@pytest.fixture
def auth_client(demo_settings, monkeypatch):
    from app.auth import router as router_module

    profile = OAuthProfile(
        provider="google", subject="sub-1", email="a@b.c", name="Ada", avatar=None
    )

    async def fake_exchange(request, provider):
        return dataclasses.replace(
            profile, provider=provider, subject=request.query_params["sub"]
        )

    monkeypatch.setattr(router_module, "_complete_exchange", fake_exchange)
    try:
        with TestClient(create_app(demo_settings), base_url=CLIENT_BASE_URL) as client:
            yield client
    finally:
        asyncio.run(_drop_schema(demo_settings.database_url, demo_settings.db_schema))


def _portfolio(client) -> dict:
    return client.get("/api/portfolio").json()


def _sign_in(client, provider: str = "google", sub: str = "sub-1"):
    return client.get(
        f"/api/auth/callback/{provider}?sub={sub}", follow_redirects=False
    )


class TestDemoClearing:
    def test_a_guest_starts_on_the_demo(self, auth_client, demo_settings):
        """The premise every other test here rests on."""
        before = _portfolio(auth_client)
        assert len(before["positions"]) == 4
        assert before["cash_balance"] == 4099.00

    def test_an_untouched_guest_loses_the_demo_on_sign_in(
        self, auth_client, demo_settings
    ):
        """The showroom is not what an account should start as."""
        _portfolio(auth_client)  # mints the guest and its demo
        _sign_in(auth_client)

        after = _portfolio(auth_client)
        assert after["positions"] == []
        assert after["cash_balance"] == demo_settings.initial_cash
        assert auth_client.get("/api/portfolio/trades").json()["trades"] == []
        assert auth_client.get("/api/auth/me").json()["kind"] == "user"

    def test_a_guest_who_traded_keeps_their_portfolio(self, auth_client):
        """PROMOTE exists to carry a guest's work into their account."""
        _portfolio(auth_client)
        auth_client.post(
            "/api/portfolio/trade",
            json={"ticker": "GOOGL", "side": "buy", "quantity": 1},
        )
        _sign_in(auth_client)

        after = _portfolio(auth_client)
        assert any(p["ticker"] == "GOOGL" for p in after["positions"])
        assert len(after["positions"]) == 5

    def test_a_second_provider_on_an_existing_account_keeps_everything(
        self, auth_client
    ):
        """The edge that makes the guest check non-negotiable.

        PROMOTE fires here too -- a signed-in session, an identity nothing is
        linked to yet -- and `decide()` reports session_has_activity=False,
        because it only computes that value for guests. A rule keyed on
        activity alone would read that False and delete this user's holdings.
        """
        _portfolio(auth_client)
        _sign_in(auth_client, "google", "sub-1")
        auth_client.post(
            "/api/portfolio/trade",
            json={"ticker": "GOOGL", "side": "buy", "quantity": 2},
        )
        held = _portfolio(auth_client)["positions"]
        assert held != []

        # Same browser, same account, second provider.
        _sign_in(auth_client, "github", "gh-sub-1")

        assert _portfolio(auth_client)["positions"] == held

    def test_signing_in_on_a_fresh_browser_creates_a_clean_account(self, auth_client):
        """CREATE mints a guest to build on, so it seeds a demo too -- and
        must clear it for exactly the same reason PROMOTE does."""
        auth_client.post("/api/auth/logout")
        _sign_in(auth_client, "google", "sub-new")

        after = _portfolio(auth_client)
        assert after["positions"] == []
```

`CLIENT_BASE_URL` and `_drop_schema` are already exported from `tests/conftest.py` — `test_auth_routes.py` imports both the same way.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/auth/test_demo_clearing.py -v
```

Expected: FAIL — the first test finds the demo positions still present.

- [ ] **Step 3: Implement the clear**

In `backend/app/auth/router.py`, add above `oauth_callback`:

```python
async def _clear_demo_if_untouched(request: Request, user_id: str, was_guest: bool) -> None:
    """Drop a seeded demo portfolio as an account becomes real.

    Two conditions, and the first one is why this is not simply
    `if not has_activity`. PROMOTE also fires when an ALREADY SIGNED-IN user
    connects a second provider, and `decide()` reports
    `session_has_activity=False` for them -- it only computes that value for
    guests. Keyed on activity alone, connecting GitHub to an existing Google
    account would silently delete that user's portfolio.

    Never fatal. The identity is already linked by the time this runs, so a
    raise here would fail a sign-in that has actually succeeded. A demo left
    behind is cosmetic; a sign-in that 500s is not.
    """
    if not was_guest:
        return
    store = request.app.state.user_store
    if await store.has_activity(user_id):
        return
    try:
        await build_reset_service(request, user_id).reset_to_clean()
    except Exception:
        logger.exception("Could not clear the demo for %s; the sign-in stands", user_id)
```

`ResetService` is built per request through `deps.get_reset_service`, which depends on `CurrentUserDep` and so cannot be used here — the callback has no resolved user yet. Add a plain constructor helper in `app/system/service.py`, and import it into `app/auth/router.py`:

```python
def build_reset_service(request, user_id: str) -> ResetService:
    """A ResetService for a user id, without going through CurrentUserDep.

    The OAuth callback resolves its own session rather than depending on
    `get_current_user` -- minting a guest mid-callback is precisely what it
    must not do -- so it needs this seam. `deps.get_reset_service` calls it
    too, so the argument list exists once.
    """
    state = request.app.state
    return ResetService(
        state.db, state.settings, user_id, state.reconciler,
        state.trade_lock, state.watchlist_lock,
    )
```

Refactor `deps.get_reset_service` to `return build_reset_service(request, user.id)`.

Then split `ResetService.reset` so both callers share one transaction rather than two copies of it. Rename the existing method's body to `_reset(self, demo: bool)`, replacing the kind lookup added in Task 3 with the parameter, and add the two public entry points:

```python
    async def reset(self) -> None:
        """Wipe this user's state and re-seed them as their kind implies.

        A guest gets the demo back, because the demo IS their seeded starting
        state. A signed-in account does not: once the account is real,
        "reset" should not hand back a portfolio they never placed.
        """
        kind_row = await self._db.fetch_one(
            "SELECT kind FROM users_profile WHERE id = ?", (self._user_id,)
        )
        demo = (
            self._settings.demo_portfolio
            and kind_row is not None
            and kind_row["kind"] == "guest"
        )
        await self._reset(demo=demo)

    async def reset_to_clean(self) -> None:
        """Wipe this user's state and re-seed them WITHOUT the demo.

        What a guest's demo becomes at the moment their account turns real.
        """
        await self._reset(demo=False)

    async def _reset(self, demo: bool) -> None:
        ...  # the existing reset() body, with `demo=demo` on the seed_user call
```

Then in `oauth_callback`, after the promote/attach block and before building the response:

```python
    if decision.outcome in (Outcome.PROMOTE, Outcome.CREATE):
        was_guest = decision.outcome is Outcome.CREATE or (
            session is not None and session.kind == "guest"
        )
        await store.promote(target_id, profile.email, profile.name, profile.avatar)
        await store.attach_identity(target_id, profile.provider, profile.subject, profile.email)
        await _clear_demo_if_untouched(request, target_id, was_guest)
```

Note `was_guest` is computed **before** `promote`, which flips `kind` to `"user"` — reading it afterwards would always be false and the demo would never clear.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/auth/ -v
```

Expected: PASS, including every pre-existing auth test.

- [ ] **Step 5: Run the full backend suite**

```bash
cd backend && uv run pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/router.py backend/app/system/service.py \
        backend/app/deps.py backend/tests/auth/test_demo_clearing.py
git commit -m "$(cat <<'EOF'
Hand a new account a clean slate, not the showroom

Signing in clears the seeded demo -- but only when the session is a guest
AND has done nothing of its own. Both halves matter. PROMOTE also fires
when a signed-in user connects a second provider, and decide() reports
no activity for them because it only computes that for guests; keyed on
activity alone this would have deleted a real portfolio on the day
someone added GitHub to their Google account.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 5: `replay_realized`

Pure function, no I/O. Independent of Tasks 2-4.

**Files:**
- Modify: `backend/app/portfolio/formulas.py`
- Test: `backend/tests/portfolio/test_formulas.py`

**Interfaces:**
- Consumes: existing `buy_avg_cost`, `realized_pnl`, `round_quantity`, `EPSILON`
- Produces: `replay_realized(trades: list[Trade]) -> dict[str, float | None]`, keyed by trade id, `None` for every buy

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/portfolio/test_formulas.py`:

```python
def _trade(id_, ticker, side, quantity, price):
    return Trade(
        id=id_, ticker=ticker, side=side, quantity=quantity, price=price,
        executed_at="2026-09-05T10:00:00Z",
    )


def test_replay_realized_carries_the_basis_across_trades():
    """Two buys at different prices, then a partial sell and a full one."""
    realized = replay_realized([
        _trade("t1", "AAPL", "buy", 10, 100.0),
        _trade("t2", "AAPL", "buy", 10, 120.0),   # avg cost now 110
        _trade("t3", "AAPL", "sell", 5, 130.0),   # (130-110)*5
        _trade("t4", "AAPL", "sell", 15, 90.0),   # (90-110)*15
    ])

    assert realized["t1"] is None
    assert realized["t2"] is None
    assert realized["t3"] == 100.0
    assert realized["t4"] == -300.0


def test_replay_realized_resets_the_basis_after_a_full_liquidation():
    """A re-buy starts a new basis; carrying the old one would misreport it."""
    realized = replay_realized([
        _trade("t1", "AAPL", "buy", 10, 100.0),
        _trade("t2", "AAPL", "sell", 10, 120.0),
        _trade("t3", "AAPL", "buy", 10, 200.0),
        _trade("t4", "AAPL", "sell", 10, 210.0),
    ])
    assert realized["t2"] == 200.0
    assert realized["t4"] == 100.0


def test_replay_realized_keeps_tickers_apart():
    realized = replay_realized([
        _trade("t1", "AAPL", "buy", 10, 100.0),
        _trade("t2", "MSFT", "buy", 10, 400.0),
        _trade("t3", "AAPL", "sell", 10, 110.0),
    ])
    assert realized["t3"] == 100.0


def test_replay_realized_tolerates_a_sell_with_no_basis():
    """Unreachable through the service, which refuses short selling -- but a
    read must not fail because a hand-edited row is odd."""
    realized = replay_realized([_trade("t1", "AAPL", "sell", 5, 50.0)])
    assert realized["t1"] == 250.0
```

Add `from app.portfolio.models import Trade` and `replay_realized` to the file's imports.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/portfolio/test_formulas.py -v
```

Expected: FAIL with `ImportError: cannot import name 'replay_realized'`.

- [ ] **Step 3: Implement it**

Append to `backend/app/portfolio/formulas.py`:

```python
def replay_realized(trades: list[Trade]) -> dict[str, float | None]:
    """Realized P&L per trade id, by replaying the log oldest-first.

    Computed, never stored (D-57): `trades` is authoritative and positions
    are a projection of it, so the basis a sell closed against is always
    recoverable from the rows before it.

    Callers must pass the WHOLE log, not a page of it. A sell's basis depends
    on every buy that came before, so replaying a `limit`-truncated list
    reports the wrong number on the oldest sells shown -- which are exactly
    the ones a user scrolls back to check.

    Buys map to None rather than 0.0: a buy realizes nothing, and 0.0 would
    render as "broke even".
    """
    basis: dict[str, tuple[float, float]] = {}  # ticker -> (quantity, avg_cost)
    out: dict[str, float | None] = {}

    for trade in trades:
        quantity, avg_cost = basis.get(trade.ticker, (0.0, 0.0))
        if trade.side == "buy":
            basis[trade.ticker] = (
                round_quantity(quantity + trade.quantity),
                buy_avg_cost(quantity, avg_cost, trade.quantity, trade.price),
            )
            out[trade.id] = None
            continue

        out[trade.id] = realized_pnl(trade.quantity, avg_cost, trade.price)
        remaining = round_quantity(quantity - trade.quantity)
        # Below epsilon the position is closed, and the next buy must start a
        # fresh basis rather than inherit this one.
        basis[trade.ticker] = (0.0, 0.0) if remaining <= EPSILON else (remaining, avg_cost)

    return out
```

Add `Trade` to the module's `from .models import ...` line.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/portfolio/test_formulas.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/portfolio/formulas.py backend/tests/portfolio/test_formulas.py
git commit -m "$(cat <<'EOF'
Work out what each sale actually made

Realized P&L is recoverable from the trade log, which is already the
authoritative record, so it is replayed rather than stored. The whole log
goes in, never a page of it: a sell's basis depends on every buy before
it, and a truncated replay misreports precisely the oldest rows a user
scrolls back to check.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 6: `GET /api/portfolio/trades`

**Files:**
- Modify: `backend/app/portfolio/repository.py` (`TradeRepository.list_all`)
- Modify: `backend/app/portfolio/service.py` (`TradeService.get_trades`)
- Modify: `backend/app/portfolio/router.py`
- Create: `backend/tests/portfolio/test_trades_route.py`

**Interfaces:**
- Consumes: `replay_realized` from Task 5
- Produces:
  - `TradeRepository.list_all() -> list[Trade]` — oldest first, unbounded
  - `TradeService.get_trades(limit: int = 200) -> list[dict]` — newest first, each with `value` and `realized_pnl`
  - `GET /api/portfolio/trades?limit=` → `{"trades": [...]}`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/portfolio/test_trades_route.py`:

```python
"""GET /api/portfolio/trades."""

import pytest


@pytest.mark.asyncio
async def test_trades_route_returns_newest_first_with_realized_pnl(api_client):
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 4})

    body = api_client.get("/api/portfolio/trades").json()
    trades = body["trades"]

    assert [t["side"] for t in trades] == ["sell", "buy"]
    assert trades[1]["realized_pnl"] is None, "a buy realizes nothing, and 0 would read as break-even"
    assert trades[0]["realized_pnl"] is not None
    assert trades[0]["value"] == round(trades[0]["quantity"] * trades[0]["price"], 2)


@pytest.mark.asyncio
async def test_trades_route_limit_does_not_change_the_realized_figures(api_client):
    """The replay runs over the whole log, so paging cannot move a number."""
    for _ in range(3):
        api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 2}
        )
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 5})

    full = api_client.get("/api/portfolio/trades").json()["trades"]
    paged = api_client.get("/api/portfolio/trades?limit=1").json()["trades"]

    assert len(paged) == 1
    assert paged[0]["realized_pnl"] == full[0]["realized_pnl"]


@pytest.mark.asyncio
async def test_trades_route_rejects_an_out_of_range_limit(api_client):
    assert api_client.get("/api/portfolio/trades?limit=0").status_code == 422
    assert api_client.get("/api/portfolio/trades?limit=501").status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/portfolio/test_trades_route.py -v
```

Expected: FAIL with 404 — the route does not exist.

- [ ] **Step 3: Add the repository read**

In `backend/app/portfolio/repository.py`, beside `list_recent`:

```python
    async def list_all(self) -> list[Trade]:
        """The whole log, oldest first, for a realized-P&L replay.

        Unbounded on purpose: `replay_realized` needs every row before a sell
        to know what basis it closed against, so a LIMIT here would produce
        wrong numbers rather than fewer of them. Bounded in practice by the
        guest expiry the cleanup cron applies.
        """
        rows = await self._db.fetch_all(
            """
            SELECT id, ticker, side, quantity, price, executed_at
            FROM trades WHERE user_id = ?
            ORDER BY executed_at ASC, seq ASC
            """,
            (self._user_id,),
        )
        return [
            Trade(
                id=row["id"],
                ticker=row["ticker"],
                side=row["side"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                executed_at=row["executed_at"],
            )
            for row in rows
        ]
```

- [ ] **Step 4: Add the service method**

In `backend/app/portfolio/service.py`, beside `get_history`:

```python
    async def get_trades(self, limit: int = 200) -> list[dict]:
        """The trade log, newest first, each row carrying what it realized.

        The replay runs over the whole log and the slice happens afterwards,
        so `limit` changes how many rows come back and never what they say.
        """
        log = await self._trades.list_all()
        realized = replay_realized(log)
        return [
            {
                **trade.to_dict(),
                "value": market_value(trade.quantity, trade.price),
                "realized_pnl": realized[trade.id],
            }
            for trade in reversed(log)
        ][:limit]
```

Add `market_value` and `replay_realized` to the module's `from .formulas import (...)` block.

- [ ] **Step 5: Add the route**

In `backend/app/portfolio/router.py`, below `get_history`:

```python
#: Upper bound on trade rows returned in one call.
MAX_TRADES_LIMIT = 500


@router.get("/trades")
async def get_trades(
    service: TradeServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_TRADES_LIMIT)] = 200,
) -> dict:
    """Executed trades, newest first, with realized P&L on each sale."""
    return {"trades": await service.get_trades(limit=limit)}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/portfolio/ -v
```

Expected: PASS.

- [ ] **Step 7: Run the full backend suite**

```bash
cd backend && uv run pytest -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/portfolio/ backend/tests/portfolio/test_trades_route.py
git commit -m "$(cat <<'EOF'
Serve the trade log, with what each sale made

The replay runs over the whole log and the slice happens afterwards, so
limit changes how many rows come back and never what any of them says.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 7: Trades on the frontend store

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api/endpoints.ts`
- Modify: `frontend/store/usePortfolioStore.ts`
- Test: `frontend/__tests__/store/usePortfolioStore.test.ts`

**Interfaces:**
- Consumes: `GET /api/portfolio/trades` from Task 6
- Produces:
  - `TradeRecord { id, ticker, side: "buy" | "sell", quantity, price, executedAt, value, realizedPnl: number | null }`
  - `fetchTrades(limit?: number): Promise<TradeRecord[]>`
  - `usePortfolioStore` gains `trades: TradeRecord[]`, `tradesStatus: LoadState`, `refreshTrades: () => Promise<void>`

- [ ] **Step 1: Write the failing test**

Append to `frontend/__tests__/store/usePortfolioStore.test.ts`, mirroring how the file already mocks `@/lib/api/endpoints`:

```ts
it("records a failed trade-log fetch rather than leaving it pending", async () => {
  vi.mocked(fetchTrades).mockRejectedValueOnce(new Error("offline"));

  await expect(usePortfolioStore.getState().refreshTrades()).rejects.toThrow();
  expect(usePortfolioStore.getState().tradesStatus).toBe("failed");
});

it("refreshes the trade log after a fill, so history is current", async () => {
  // `receipt` is the TradeReceipt fixture this file already builds for its
  // existing trade tests — reuse it rather than defining a second one.
  vi.mocked(executeTrade).mockResolvedValueOnce(receipt);
  await usePortfolioStore.getState().trade("AAPL", "buy", 1);
  expect(fetchTrades).toHaveBeenCalled();
});
```

Add `fetchTrades` to the file's `vi.mock("@/lib/api/endpoints", ...)` factory and to its import list, following the shape already there for `fetchPortfolioHistory`.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npm test -- --run __tests__/store/usePortfolioStore.test.ts
```

Expected: FAIL — `refreshTrades` is not a function.

- [ ] **Step 3: Add the type**

In `frontend/lib/types.ts`, beside `SnapshotPoint`:

```ts
/** One executed fill, as the history view renders it. */
export interface TradeRecord {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executedAt: string;
  /** quantity × price, rounded server-side so the column always adds up. */
  value: number;
  /** Null on every buy — a buy realizes nothing, and 0 would read as
   *  "broke even". The table prints an em dash for it. */
  realizedPnl: number | null;
}
```

- [ ] **Step 4: Add the endpoint**

In `frontend/lib/api/endpoints.ts`, beside `fetchPortfolioHistory`:

```ts
export async function fetchTrades(limit = 200): Promise<TradeRecord[]> {
  const raw = await api.get<{
    trades: {
      id: string;
      ticker: string;
      side: "buy" | "sell";
      quantity: number;
      price: number;
      executed_at: string;
      value: number;
      realized_pnl: number | null;
    }[];
  }>(`/api/portfolio/trades?limit=${limit}`);
  return raw.trades.map((t) => ({
    id: t.id,
    ticker: t.ticker,
    side: t.side,
    quantity: t.quantity,
    price: t.price,
    executedAt: t.executed_at,
    value: t.value,
    realizedPnl: t.realized_pnl,
  }));
}
```

Add `TradeRecord` to the file's type import list.

- [ ] **Step 5: Add the store slice**

In `frontend/store/usePortfolioStore.ts`, add to the interface, the initial state, and the actions:

```ts
  trades: TradeRecord[];
  /** Tracked separately for the same reason `historyStatus` is: the trade log
   *  comes from its own endpoint, fetched by the history page rather than by
   *  the boot sequence, so `status` says nothing about whether it has landed. */
  tradesStatus: LoadState;
  refreshTrades: () => Promise<void>;
```

```ts
  trades: [],
  tradesStatus: "pending" as LoadState,
```

```ts
  refreshTrades: async () => {
    try {
      set({ trades: await fetchTrades(), tradesStatus: "ready" });
    } catch (error) {
      set({ tradesStatus: "failed" });
      throw error;
    }
  },
```

And add it to the post-fill re-read in `trade`, so a fill shows up in history without a reload:

```ts
    await Promise.allSettled([get().refresh(), get().refreshHistory(), get().refreshTrades()]);
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd frontend && npm test -- --run
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api/endpoints.ts \
        frontend/store/usePortfolioStore.ts frontend/__tests__/store/usePortfolioStore.test.ts
git commit -m "$(cat <<'EOF'
Carry the trade log to the frontend

Its own load state, for the reason historyStatus has one: it arrives from
its own endpoint on its own page, so the portfolio's status says nothing
about whether it is here yet.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 8: The route group and the shared shell

Pure move. No panel moves between routes and no visual change — that is Task 9. Keeping them apart means a reviewer can see that the shell still works before the layout changes underneath it.

**Files:**
- Create: `frontend/app/(workspace)/layout.tsx`
- Create: `frontend/app/(workspace)/page.tsx`
- Delete: `frontend/app/page.tsx`
- Modify: `backend/tests/test_api.py` (`TestExportedSubroutes`)

**Interfaces:**
- Consumes: `useAppBoot` from Task 1
- Produces: a layout that mounts `usePriceStream()` and `useAppBoot()` once for `/`, `/portfolio/` and `/history/`

- [ ] **Step 1: Create the shell**

`frontend/app/(workspace)/layout.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { usePriceStream } from "@/lib/stream/usePriceStream";
import { useAppBoot } from "@/lib/useAppBoot";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";
import { useSessionStore } from "@/store/useSessionStore";
import { Header } from "@/components/layout/Header";
import { Rail } from "@/components/layout/Rail";
import { Footer } from "@/components/layout/Footer";
import { ThemeSync } from "@/components/layout/ThemeSync";
import { BootScreen } from "@/components/layout/BootScreen";
import { ClaimConflictDialog } from "@/components/layout/ClaimConflictDialog";
import { TradeReceiptDialog } from "@/components/trade/TradeReceiptDialog";

/**
 * The workspace shell, shared by every route in this group.
 *
 * It is a layout rather than something each page renders so that navigating
 * between Overview, Portfolio and History does not remount it: one
 * EventSource stays open across the whole workspace, and the lazily-imported
 * chart bundles stay warm. A per-page shell would reconnect the stream and
 * re-download a chart bundle on every tab switch, which is the objection that
 * usually makes real routes a bad trade — this is what answers it.
 *
 * `/privacy/` sits outside the group deliberately: a reading page has no
 * business holding a price stream open.
 */
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  usePriceStream();

  const refreshWatchlist = useWatchlistStore((s) => s.refresh);
  const refreshPortfolio = usePortfolioStore((s) => s.refresh);
  const refreshChat = useChatStore((s) => s.refresh);
  const sessionVersion = useSessionStore((s) => s.sessionVersion);
  const loadSession = useSessionStore((s) => s.load);

  const booted = useAppBoot();

  useEffect(() => {
    if (sessionVersion === 0) return;
    void refreshPortfolio().catch(() => {});
    void refreshWatchlist().catch(() => {});
    void refreshChat().catch(() => {});
    void loadSession().catch(() => {});
  }, [sessionVersion, refreshPortfolio, refreshWatchlist, refreshChat, loadSession]);

  useEffect(() => {
    const timer = setInterval(() => void refreshPortfolio().catch(() => {}), 15_000);
    return () => clearInterval(timer);
  }, [refreshPortfolio]);

  return (
    <div
      data-booting={booted ? undefined : ""}
      className="flex min-h-screen flex-col gap-3 p-3 lg:h-screen lg:flex-row"
    >
      <ThemeSync />
      <BootScreen done={booted} />
      <ClaimConflictDialog />
      <TradeReceiptDialog />
      <Rail />

      <div className="flex min-w-0 flex-1 flex-col gap-3 lg:min-h-0">
        <Header />
        {children}
        <Footer />
      </div>
    </div>
  );
}
```

Carry over the explanatory comments that live on these effects in the current `app/page.tsx` — the `sessionVersion` one and the "positions change only on a trade" one. Do not drop them.

- [ ] **Step 2: Move the page**

`git mv frontend/app/page.tsx "frontend/app/(workspace)/page.tsx"`, then strip from it everything the layout now owns: the `usePriceStream` call, both effects, `useAppBoot`, the outer `<div>`, `ThemeSync`, `BootScreen`, both dialogs, `Rail`, `Header`, `Footer`. What remains is the `<main>` element and the three dynamic chart imports. Keep the `<main>` grid exactly as it is for now.

- [ ] **Step 3: Build and check the routes exist**

```bash
cd frontend && npm run build
ls out/index.html
```

Expected: the build succeeds and `out/index.html` exists. A route group must not add a path segment — if you see `out/workspace/`, the directory was named without parentheses.

- [ ] **Step 4: Run the frontend suite**

```bash
cd frontend && npm test -- --run
```

Expected: PASS. Any test that rendered `app/page.tsx` directly needs its import path updated, not its assertions.

- [ ] **Step 5: Add the future routes to the backend guard**

In `backend/tests/test_api.py`, `TestExportedSubroutes` currently asserts `/privacy/` in both spellings. Parametrize it over `("privacy", "portfolio", "history")` so the two routes Task 9 adds are guarded the moment they exist. Read the class first and follow its existing fixture and assertion style.

Expected at this point: the `portfolio` and `history` cases FAIL, because the pages do not exist yet. Mark them `pytest.mark.xfail(reason="added in the routes task", strict=True)` and remove the marker in Task 9 — a guard that is written after the trap has already been walked into is not a guard.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/app backend/tests/test_api.py
git commit -m "$(cat <<'EOF'
Give the workspace a shell that survives navigation

A route group, so Overview, Portfolio and History share one layout
instance: one EventSource across the whole workspace and chart bundles
that stay warm, rather than a reconnect and a re-download per tab. That
cost is the usual reason real routes are the wrong trade here, and this
is what removes it. /privacy/ stays outside -- a reading page has no
business holding a price stream open.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 9: Split the panels across three routes

**Files:**
- Modify: `frontend/app/(workspace)/page.tsx`
- Create: `frontend/app/(workspace)/portfolio/page.tsx`
- Create: `frontend/app/(workspace)/history/page.tsx` (placeholder until Task 10)
- Modify: `frontend/components/layout/Rail.tsx`
- Modify: `frontend/components/layout/panels.ts`
- Test: `frontend/__tests__/components/Rail.test.tsx` (new)
- Modify: `backend/tests/test_api.py` (drop the xfail markers)

**Interfaces:**
- Consumes: the shell from Task 8
- Produces: `PANELS` re-keyed to `{ watchlist, chart, assistant }`; `NAV: { href, label, icon }[]` exported from `panels.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/__tests__/components/Rail.test.tsx`:

```tsx
import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Rail } from "@/components/layout/Rail";

vi.mock("next/navigation", () => ({ usePathname: () => "/portfolio/" }));

it("marks the route being viewed", () => {
  render(<Rail />);
  expect(screen.getByRole("link", { name: /portfolio/i })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("link", { name: /overview/i })).not.toHaveAttribute("aria-current");
});

it("links to all three workspace routes", () => {
  render(<Rail />);
  expect(screen.getByRole("link", { name: /overview/i })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: /portfolio/i })).toHaveAttribute("href", "/portfolio/");
  expect(screen.getByRole("link", { name: /history/i })).toHaveAttribute("href", "/history/");
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- --run __tests__/components/Rail.test.tsx
```

Expected: FAIL — the rail renders buttons, not links.

- [ ] **Step 3: Re-key `panels.ts`**

```ts
/**
 * The panels the overview still holds, and the routes the rail navigates to.
 *
 * The ids survive the move from scroll targets to route pages: they are what
 * the onboarding tour points its spotlight at, and what each section anchors
 * itself with, so both sides still have to agree on the spelling.
 */
export const PANELS = {
  watchlist: { id: "panel-watchlist", label: "Watchlist", minH: "min-h-[320px]" },
  chart: { id: "panel-chart", label: "Markets", minH: "min-h-[280px]" },
  assistant: { id: "panel-assistant", label: "Assistant", minH: "min-h-[340px]" },
} as const;

export type PanelKey = keyof typeof PANELS;

export const CHART_MIN_H = "min-h-[220px]";

/** The rail's destinations. Trailing slashes match `trailingSlash: true`. */
export const NAV = [
  { href: "/", label: "Overview", icon: "M4 6h16M4 12h10M4 18h6" },
  { href: "/portfolio/", label: "Portfolio", icon: "M4 20V9m5 11V4m5 16v-7m5 7V11" },
  { href: "/history/", label: "History", icon: "M12 8v4l3 2M4 12a8 8 0 1 0 8-8 8 8 0 0 0-7.5 5.2M4 5v4h4" },
] as const;
```

`PANELS.portfolio` is being deleted, and `components/portfolio/PositionsTable.tsx` reads `PANELS.portfolio.id` for its `<section id>`. Replace that with a literal `id="panel-positions"` — the table now owns a route rather than an anchor, and nothing resolves the id any more. Compile will catch it; do not re-add the key to keep the compiler quiet.

- [ ] **Step 4: Rewrite the rail**

Replace the `<button onClick={scrollTo}>` map in `frontend/components/layout/Rail.tsx` with `next/link` entries over `NAV`, keeping the existing markup — the same svg block, the same `aria-label`, the same `lg:hidden` label rule, the same badge span. Add:

```tsx
const pathname = usePathname();
```

and per entry:

```tsx
<Link
  key={item.href}
  href={item.href}
  aria-label={item.label}
  aria-current={pathname === item.href ? "page" : undefined}
  className={`group flex flex-1 items-center gap-2 rounded-control px-2 py-1.5 text-left transition lg:flex-none ${
    pathname === item.href ? "bg-blue-wash" : "hover:bg-surface-sunk"
  }`}
>
```

Delete the now-unused `scrollTo` helper and the `ICONS` map (the paths moved to `NAV`). Keep the badges, re-keyed: Overview → watchlist count, Portfolio → position count, History → trade count. Keep the em-dash placeholder for a count that has not arrived, and its comment.

- [ ] **Step 5: Slim the overview**

In `frontend/app/(workspace)/page.tsx`, delete the `PortfolioHeatmap`, `PnlChart` and `PositionsTable` imports, their dynamic wrappers, and their JSX. The middle column drops to two rows:

```tsx
        <main className="grid flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
          <div className="flex min-w-0 flex-col lg:min-h-0">
            <WatchlistPanel />
          </div>

          {/* The ticket's row is `auto`, so it is subtracted before the
              fraction is shared out and the chart takes everything else --
              which is the whole point of moving the portfolio panels to
              their own route. */}
          <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 lg:grid-rows-[minmax(0,1fr)_auto]">
            <MainChart ticker={selectedTicker} />
            <TradeBar />
          </div>

          <div className="flex min-w-0 flex-col lg:min-h-0">
            <ChatPanel />
          </div>
        </main>
```

- [ ] **Step 6: Create the portfolio route**

`frontend/app/(workspace)/portfolio/page.tsx`:

```tsx
"use client";

import dynamic from "next/dynamic";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { CHART_MIN_H } from "@/components/layout/panels";

const PnlChart = dynamic(
  () => import("@/components/portfolio/PnlChart").then((m) => m.PnlChart),
  { ssr: false, loading: () => <div className={`card ${CHART_MIN_H} lg:min-h-0`} /> },
);
const PortfolioHeatmap = dynamic(
  () => import("@/components/portfolio/PortfolioHeatmap").then((m) => m.PortfolioHeatmap),
  { ssr: false, loading: () => <div className={`card ${CHART_MIN_H} lg:min-h-0`} /> },
);

/**
 * The portfolio, at the size it needs to be read.
 *
 * On the overview these three shared one column with the main chart and the
 * trade ticket, which left the heatmap and the performance chart resolving to
 * less than Recharts' own axes occupy. Here the charts get half the width
 * each and the table gets all of it.
 */
export default function PortfolioPage() {
  return (
    <main className="grid flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-rows-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-2">
        <PortfolioHeatmap />
        <PnlChart />
      </div>
      <PositionsTable />
    </main>
  );
}
```

- [ ] **Step 7: Create a placeholder history route**

`frontend/app/(workspace)/history/page.tsx` — a `<main>` holding a card with the heading "History" and nothing else. Task 10 fills it. It exists now so the exported-route guard from Task 8 can go green.

- [ ] **Step 8: Drop the xfail markers**

Remove `pytest.mark.xfail` from the `portfolio` and `history` cases in `TestExportedSubroutes`.

- [ ] **Step 9: Build, then run both suites**

```bash
cd frontend && npm run build && ls out/portfolio/index.html out/history/index.html
npm test -- --run
cd ../backend && uv run pytest -q
```

Expected: all three PASS. The backend test needs the frontend built — check whether `TestExportedSubroutes` builds it or skips without it, and follow whatever that class already does.

- [ ] **Step 10: Commit**

```bash
git add -A frontend backend/tests/test_api.py
git commit -m "$(cat <<'EOF'
Give the portfolio a page of its own

The heatmap and the performance chart were sharing one column with the
main chart and the trade ticket, and resolved to less height than
Recharts' own axes occupy. Moving them to /portfolio/ is what gives both
them and the chart room; enlarging them in place could not, because they
were all competing for the same column.

The rail stops scrolling to anchors and starts navigating.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 10: The history table

**Files:**
- Create: `frontend/components/portfolio/TradeHistoryTable.tsx`
- Modify: `frontend/app/(workspace)/history/page.tsx`
- Test: `frontend/__tests__/components/TradeHistoryTable.test.tsx`

**Interfaces:**
- Consumes: `TradeRecord`, `usePortfolioStore.trades / tradesStatus / refreshTrades` from Task 7
- Produces: `<TradeHistoryTable />`

- [ ] **Step 1: Write the failing test**

`frontend/__tests__/components/TradeHistoryTable.test.tsx`:

```tsx
import { beforeEach, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { TradeHistoryTable } from "@/components/portfolio/TradeHistoryTable";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import type { TradeRecord } from "@/lib/types";

const sell: TradeRecord = {
  id: "t1", ticker: "NVDA", side: "sell", quantity: 4, price: 874.5,
  executedAt: "2026-09-05T14:32:07Z", value: 3498, realizedPnl: 212.4,
};
const buy: TradeRecord = {
  id: "t2", ticker: "AAPL", side: "buy", quantity: 12, price: 190.11,
  executedAt: "2026-09-05T14:28:51Z", value: 2281.32, realizedPnl: null,
};

beforeEach(() => {
  usePortfolioStore.setState({
    trades: [sell, buy],
    tradesStatus: "ready",
    refreshTrades: async () => {},
  });
});

it("names each side in the tense that is true", () => {
  render(<TradeHistoryTable />);
  expect(screen.getByText("Sold")).toBeInTheDocument();
  expect(screen.getByText("Bought")).toBeInTheDocument();
});

it("carries a sign and a glyph on a realized value, so colour is never the only encoding", () => {
  render(<TradeHistoryTable />);
  const row = screen.getByRole("row", { name: /NVDA/ });
  expect(within(row).getByText(/▲/)).toBeInTheDocument();
  expect(within(row).getByText(/\+\$212\.40/)).toBeInTheDocument();
});

it("prints an em dash on a buy rather than a zero that reads as break-even", () => {
  render(<TradeHistoryTable />);
  const row = screen.getByRole("row", { name: /AAPL/ });
  expect(within(row).getByText("—")).toBeInTheDocument();
});

it("says so when there is nothing to show", () => {
  usePortfolioStore.setState({ trades: [], tradesStatus: "ready" });
  render(<TradeHistoryTable />);
  expect(screen.getByText(/no trades yet/i)).toBeInTheDocument();
});

it("offers a retry when the log could not be loaded", () => {
  usePortfolioStore.setState({ trades: [], tradesStatus: "failed" });
  render(<TradeHistoryTable />);
  expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- --run __tests__/components/TradeHistoryTable.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Build the component**

Model it on `frontend/components/portfolio/PositionsTable.tsx` — read that file first and match its `card` / `card-title` shell, its `SkeletonRow` / `LoadFailure` / empty-state branch order, its sticky `thead`, and its `border-t-hairline border-border` row separators.

```tsx
"use client";

import { useEffect } from "react";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { formatIsoClock, formatPrice, formatQuantity } from "@/lib/format";
import { InstrumentLabel } from "../ui/InstrumentLabel";
import { SignedValue } from "../ui/SignedValue";
import { SkeletonRow } from "../ui/Skeleton";
import { LoadFailure } from "../ui/LoadFailure";

/**
 * Every fill, newest first, and what each sale made.
 *
 * The action column is past tense on both sides -- "Bought", "Sold" -- which
 * is how the trade receipt and the assistant's inline receipts already speak
 * about an order that has filled.
 */
export function TradeHistoryTable() {
  const trades = usePortfolioStore((s) => s.trades);
  const status = usePortfolioStore((s) => s.tradesStatus);
  const refreshTrades = usePortfolioStore((s) => s.refreshTrades);

  useEffect(() => {
    // Swallowed, not ignored: refreshTrades records the outcome on the store,
    // which is what the branch below renders.
    void refreshTrades().catch(() => {});
  }, [refreshTrades]);

  return (
    <section
      id="panel-history"
      className="rise card flex flex-1 flex-col overflow-hidden lg:min-h-0"
      aria-label="Trade history"
    >
      <header className="card-title">
        <span>History</span>
        <span className="text-[11px] font-medium text-text-muted">
          {status === "ready" ? `${trades.length} fills` : "—"}
        </span>
      </header>

      {status === "pending" ? (
        <div className="py-1">
          {Array.from({ length: 4 }, (_, i) => (
            <SkeletonRow key={`skeleton-${i}`} />
          ))}
        </div>
      ) : status === "failed" ? (
        <LoadFailure what="your trade history" onRetry={refreshTrades} />
      ) : trades.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-text-muted">
          No trades yet. Every order you place shows up here.
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full text-[13px]" data-testid="trade-history">
            <thead className="sticky top-0 bg-surface text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
              <tr>
                <th className="px-3 pb-2 pt-1 text-left">Time</th>
                <th className="px-3 pb-2 pt-1 text-left">Instrument</th>
                <th className="px-3 pb-2 pt-1 text-left">Action</th>
                <th className="px-3 pb-2 pt-1 text-right">Units</th>
                <th className="px-3 pb-2 pt-1 text-right">Price</th>
                <th className="px-3 pb-2 pt-1 text-right">Value</th>
                <th className="px-3 pb-2 pt-1 text-right">Realized</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr
                  key={trade.id}
                  className="border-t-hairline border-border"
                  data-testid={`trade-${trade.id}`}
                >
                  <td className="px-3 py-2 text-text-muted">
                    {formatIsoClock(trade.executedAt)}
                  </td>
                  <td className="px-3 py-2">
                    <InstrumentLabel ticker={trade.ticker} />
                  </td>
                  <td className="px-3 py-2 font-medium">
                    {trade.side === "buy" ? "Bought" : "Sold"}
                  </td>
                  <td className="px-3 py-2 text-right">{formatQuantity(trade.quantity)}</td>
                  <td className="px-3 py-2 text-right text-text-muted">
                    {formatPrice(trade.price)}
                  </td>
                  <td className="px-3 py-2 text-right font-semibold">
                    {formatPrice(trade.value)}
                  </td>
                  <td className="px-3 py-2 text-right font-semibold">
                    {/* A buy realizes nothing. An em dash says that; a 0.00
                        would read as "broke even", which is a different claim. */}
                    {trade.realizedPnl === null ? (
                      <span aria-label="not applicable">&mdash;</span>
                    ) : (
                      <SignedValue value={trade.realizedPnl} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
```

Check that `formatIsoClock` exists in `lib/format.ts` with that name — `PnlChart` imports it — and that `SignedValue` renders both the sign and the arrow glyph. If it renders only the sign, the glyph rule is not satisfied and the test above will say so.

- [ ] **Step 4: Fill in the route**

Replace the placeholder in `frontend/app/(workspace)/history/page.tsx`:

```tsx
"use client";

import { TradeHistoryTable } from "@/components/portfolio/TradeHistoryTable";

/** Every fill, newest first, and what each sale made. */
export default function HistoryPage() {
  return (
    <main className="flex flex-1 flex-col lg:min-h-0">
      <TradeHistoryTable />
    </main>
  );
}
```

- [ ] **Step 5: Check the contrast floor**

If the table introduces any foreground/background pairing not already covered, add it to `frontend/__tests__/lib/theme.test.ts` following the pairings that file already asserts. If it reuses existing tokens only, say so in the commit body rather than adding a redundant assertion.

- [ ] **Step 6: Run the suite and build**

```bash
cd frontend && npm test -- --run && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/portfolio/TradeHistoryTable.tsx \
        "frontend/app/(workspace)/history/page.tsx" \
        frontend/__tests__/components/TradeHistoryTable.test.tsx
git commit -m "$(cat <<'EOF'
Show what was traded, and what it made

Past tense on both sides, the way the receipt and the assistant already
speak. A buy realizes nothing, so it gets an em dash rather than a zero
the reader has to interpret as break-even.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 11: The onboarding tour

**Files:**
- Create: `frontend/components/onboarding/steps.ts`
- Create: `frontend/components/onboarding/Tour.tsx`
- Modify: `frontend/app/(workspace)/page.tsx` (render it)
- Test: `frontend/__tests__/components/Tour.test.tsx`

**Interfaces:**
- Consumes: `PANELS` ids from Task 9, `useSessionStore.session`
- Produces: `<Tour />`, `TOUR_STORAGE_KEY = "trader-tour-seen"`

- [ ] **Step 1: Write the failing test**

`frontend/__tests__/components/Tour.test.tsx`:

```tsx
import { beforeEach, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Tour, TOUR_STORAGE_KEY } from "@/components/onboarding/Tour";
import { useSessionStore } from "@/store/useSessionStore";

function asGuest() {
  useSessionStore.setState({
    status: "ready",
    session: { id: "g1", kind: "guest", email: null, name: null, avatar: null, hasActivity: false },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  // The steps point at real ids; without them every step is skipped.
  document.body.innerHTML = `
    <div id="panel-watchlist"></div><div id="panel-chart"></div>
    <div id="panel-assistant"></div><div id="rail-portfolio"></div>`;
  asGuest();
});

it("greets a signed-out visitor", () => {
  render(<Tour />);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("stays away from a signed-in user, who has seen the app", () => {
  useSessionStore.setState({
    session: { id: "u1", kind: "user", email: "a@b.c", name: "A", avatar: null, hasActivity: true },
  });
  render(<Tour />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("does not come back once it has been dismissed", () => {
  window.localStorage.setItem(TOUR_STORAGE_KEY, "1");
  render(<Tour />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("closes on Skip, and remembers", () => {
  render(<Tour />);
  fireEvent.click(screen.getByRole("button", { name: /skip/i }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(window.localStorage.getItem(TOUR_STORAGE_KEY)).toBe("1");
});

it("closes on Escape", () => {
  render(<Tour />);
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("advances, and the last step ends it", () => {
  render(<Tour />);
  expect(screen.getByText(/1 of/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /next/i }));
  expect(screen.getByText(/2 of/)).toBeInTheDocument();
});

it("skips a step whose target is not on screen", () => {
  document.body.innerHTML = `<div id="panel-watchlist"></div>`;
  render(<Tour />);
  // Only the one reachable step is counted, so the tour never points at nothing.
  expect(screen.getByText("1 of 1")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- --run __tests__/components/Tour.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the steps**

`frontend/components/onboarding/steps.ts` — copy kept out of the component so it can be read and changed without touching behaviour:

```ts
import { PANELS } from "../layout/panels";

export interface TourStep {
  /** Element id to spotlight. A step whose target is absent is skipped. */
  target: string;
  title: string;
  body: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    target: PANELS.watchlist.id,
    title: "Your watchlist",
    body: "Ten tickers, streaming live. Prices flash green on an uptick and red on a downtick. Click a row to chart it.",
  },
  {
    target: PANELS.chart.id,
    title: "The chart",
    body: "Price over time for whichever symbol you picked. It takes that instrument's colour, so the chart always matches the row you clicked.",
  },
  {
    target: "trade-ticket",
    title: "Buy and sell",
    body: "Market orders, filled instantly at the live price. You are starting with a demo portfolio and virtual cash — nothing here is real money.",
  },
  {
    target: PANELS.assistant.id,
    title: "Ask the assistant",
    body: "It can read your positions, suggest trades, and place them for you. Try \"what's my riskiest position?\"",
  },
  {
    target: "rail-portfolio",
    title: "Portfolio and history",
    body: "Your holdings, allocation and performance live on the Portfolio tab; every fill you have made is on History.",
  },
];
```

Add `id="trade-ticket"` to the `TradeBar`'s root element and `id="rail-portfolio"` to the rail's Portfolio link, if they are not already there.

- [ ] **Step 4: Build the tour**

`frontend/components/onboarding/Tour.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { TOUR_STEPS, type TourStep } from "./steps";

export const TOUR_STORAGE_KEY = "trader-tour-seen";

function seen(): boolean {
  try {
    return window.localStorage.getItem(TOUR_STORAGE_KEY) !== null;
  } catch {
    // Private browsing denies storage. A first-run affordance is not state
    // worth defending, so an unreadable key means "show it".
    return false;
  }
}

/** Only the steps whose target is actually on this screen. */
function reachable(): TourStep[] {
  return TOUR_STEPS.filter((step) => document.getElementById(step.target) !== null);
}

/**
 * A guided walk around the real UI, for a visitor who has not signed in.
 *
 * The spotlight is one rect over the step's target with a 9999px box-shadow
 * standing in for a cut-out -- no clip-path, no second overlay, no library.
 */
export function Tour() {
  const session = useSessionStore((s) => s.session);
  const [steps, setSteps] = useState<TourStep[] | null>(null);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const isGuest = session?.kind === "guest";

  // Resolved once, after mount: the targets have to exist to be measured, and
  // a step pointing at nothing would spotlight a zero rect.
  useEffect(() => {
    if (!isGuest || seen()) return;
    setSteps(reachable());
  }, [isGuest]);

  const step = steps?.[index];

  useEffect(() => {
    if (!step) return;
    const measure = () => {
      const target = document.getElementById(step.target);
      setRect(target ? target.getBoundingClientRect() : null);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [step]);

  const dismiss = useCallback(() => {
    setSteps(null);
    try {
      window.localStorage.setItem(TOUR_STORAGE_KEY, "1");
    } catch {
      // The tour will show again next visit. Acceptable; storing it is a
      // convenience, not a contract.
    }
  }, []);

  useEffect(() => {
    if (!step) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, dismiss]);

  useEffect(() => {
    cardRef.current?.focus();
  }, [index]);

  if (!steps || steps.length === 0 || !step) return null;

  const last = index === steps.length - 1;

  return (
    <div className="fixed inset-0 z-[90]">
      {rect && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute rounded-card transition-[top,left,width,height] duration-200 motion-reduce:transition-none"
          style={{
            top: rect.top - 4,
            left: rect.left - 4,
            width: rect.width + 8,
            height: rect.height + 8,
            boxShadow: "0 0 0 9999px rgb(0 0 0 / 0.45)",
          }}
        />
      )}

      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        tabIndex={-1}
        className="material absolute left-1/2 bottom-8 w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 rounded-chrome p-4 shadow-pop outline-none"
      >
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
          {index + 1} of {steps.length}
        </p>
        <h2 id="tour-title" className="mt-1 text-[15px] font-semibold tracking-[-0.01em] text-text">
          {step.title}
        </h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-text-muted">{step.body}</p>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button
            onClick={dismiss}
            className="rounded-control px-3 py-1.5 text-[13px] font-medium text-text-muted transition hover:bg-surface-sunk"
          >
            Skip
          </button>
          <button
            onClick={() => (last ? dismiss() : setIndex((i) => i + 1))}
            className="rounded-control bg-blue-fill px-3 py-1.5 text-[13px] font-semibold text-white transition hover:opacity-90"
          >
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

Check the class names against `tailwind.config.ts` before assuming them — `rounded-chrome`, `shadow-pop`, `bg-blue-fill` and `material` must all already exist. If any does not, use the token that does rather than adding a new one. `bg-blue-fill` with white text is the pairing the palette defines for exactly this (a white label on a filled button), so it clears 4.5:1 already; `text-text-muted` at 13px is likewise an asserted pairing.

- [ ] **Step 5: Render it on the overview**

Add `<Tour />` to `frontend/app/(workspace)/page.tsx`'s returned fragment. Overview only — the tour's steps point at panels that exist there.

- [ ] **Step 6: Run the suite and build**

```bash
cd frontend && npm test -- --run && npm run build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/onboarding frontend/components/layout/Rail.tsx \
        frontend/components/trade/TradeBar.tsx \
        "frontend/app/(workspace)/page.tsx" \
        frontend/__tests__/components/Tour.test.tsx
git commit -m "$(cat <<'EOF'
Walk a first-time visitor around the app

Five steps over the real UI rather than a slideshow about it. Dismissal
is remembered; reaching step three and reloading is not, because a
half-finished tour is not something to hold someone to.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

### Task 12: E2E and documentation

**Files:**
- Modify: `test/docker-compose.test.yml` (add `DEMO_PORTFOLIO=false`)
- Modify: the existing Playwright specs in `test/`
- Create: one new spec covering the demo
- Modify: `planning/PLAN.md`, `planning/API_CONTRACT.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: everything above

- [ ] **Step 1: Pin the existing suite to the old baseline**

Add `DEMO_PORTFOLIO=false` to the app service's environment in `test/docker-compose.test.yml`. The existing fresh-start scenarios assert $10,000 and no positions; those assertions are about the seeding baseline and must keep meaning what they meant. Do not relax them.

- [ ] **Step 2: Update the navigation the specs use**

Any spec that reached the positions table, the heatmap or the performance chart on `/` now has to navigate to `/portfolio/` first. Update those, and add an assertion that the rail's Portfolio link carries `aria-current="page"` once there.

- [ ] **Step 3: Add the demo scenario**

A new spec, run with `DEMO_PORTFOLIO=true`, asserting that a first load shows four positions on `/portfolio/`, a performance chart with points in it rather than the "charting starts" copy, and four rows on `/history/`. Follow the existing specs' fixture and readiness-wait style — they wait on `/api/health`, not on a sleep.

- [ ] **Step 4: Run the E2E suite**

```bash
cd test && docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

Expected: PASS.

- [ ] **Step 5: Update the planning docs**

In the dated-note style `PLAN.md` already uses (`*Revised 2026-09-05: …*`):

- §5 — `DEMO_PORTFOLIO`, and the same line in `.env.example`
- §7 — the `is_demo` column and the demo seed, replacing "Default Seed Data" for guests
- §8 — `GET /api/portfolio/trades`
- §10 — the three routes and the new panel inventory; the layout diagram; the tour
- §11 — `/portfolio/` and `/history/` named in the directory-route section

`planning/API_CONTRACT.md` — the trades endpoint's request and response shapes.

- [ ] **Step 6: Commit**

```bash
git add test/ planning/ .env.example
git commit -m "$(cat <<'EOF'
Record the routes, the demo, and the trade log

The E2E suite runs with DEMO_PORTFOLIO=false so its fresh-start
assertions keep asserting what they were written to, plus one scenario
with the demo on.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018c4gDNhcRGmFReUhKAXi4H
EOF
)"
```

---

## Verification before the PR

- [ ] `cd backend && uv run pytest -q` — PASS
- [ ] `cd frontend && npm test -- --run` — PASS
- [ ] `cd frontend && npm run build` — succeeds, and `out/index.html`, `out/portfolio/index.html`, `out/history/index.html`, `out/privacy/index.html` all exist
- [ ] `cd test && docker compose -f docker-compose.test.yml up --build --abort-on-container-exit` — PASS
- [ ] Load the app in a fresh browser context and confirm on the network panel that exactly one `Set-Cookie` for `trader_session` is issued on the first load, and that no boot request aborts
- [ ] Confirm the demo portfolio renders on `/portfolio/` with both a green and a red cell in the heatmap
