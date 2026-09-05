# A settled first load, a demo portfolio, and real navigation

**Date:** 2026-09-05
**Status:** Approved design, pending implementation plan
**Supersedes:** PLAN.md §10 (single-page workspace layout, and the panel inventory of the main
column). Adds two routes to §11's "Serving a route that is a directory", one endpoint to §8, one
column to §7's `trades` table, and one environment variable to §5.

## 1. Motivation

Three complaints, one of which turned out to have a measurable cause.

**Charts are sometimes empty on first load.** Reproduced against the live deployment. Not a chart
bug at all: the four boot requests race each other into four separate guest mints, and the losers
time out. §3.

**A signed-out visitor sees an empty app.** $10,000 in cash, no positions, one snapshot. The
heatmap has nothing to draw, the performance chart says "Charting starts once the first two
snapshots land", and the app that is meant to demonstrate an AI trading workstation demonstrates
an empty one. §4, §5.

**The portfolio is cramped.** It shares the middle column with the main chart and the trade
ticket, so the heatmap and performance chart resolve to a few hundred pixels each and the
positions table gets whatever is left. §6.

## 2. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D-50 | The boot sequence resolves the session first, then fans out | One cookie-less request means one guest mint and one cold start, instead of four of each racing |
| D-51 | The demo portfolio is seeded per guest, at mint, not offered as a button | The first paint is the thing being fixed; an opt-in button leaves it exactly as empty as it is today |
| D-52 | Signing in clears the demo — but only when the guest has no activity of their own | `PROMOTE` exists to carry a guest's portfolio into their account. Wiping a guest who actually traded would destroy real work |
| D-53 | Demo trades carry `is_demo` and are excluded from `has_activity()` | Without it every guest looks active, and the sign-in conflict dialog fires on every single sign-in — the failure `has_activity`'s own docstring warns about |
| D-54 | Backfilled snapshots are computed from `market/deterministic.price_at` | A pure function of time, so the demo's value curve is genuine on the serverless target and close enough on the container one. Exact in the deployment that has the problem |
| D-55 | Real routes, in a route group with a shared layout | Deep-linkable and shareable, without the SSE reconnect and chart-bundle remount that per-page shells would cost |
| D-56 | The overview gives up the heatmap, performance chart and positions table | Moving them to `/portfolio/` is what gives *both* the main chart and the portfolio room. Enlarging panels in place cannot, because they are competing for one column |
| D-57 | Realized P&L is computed by replaying the trade log, never stored | Matches the existing rule that `trades` is authoritative and positions are a projection (D-21) |

## 3. The first-load failure

### What happens

`useAppBoot` issues four requests in parallel on mount: `/api/auth/me`, `/api/portfolio`,
`/api/watchlist`, `/api/chat`. On a first visit none of them carries a session cookie, so each one
independently reaches `get_current_user`, finds no cookie, and calls `mint_guest()` — a
transaction of twelve inserts followed by a full `reconciler.reconcile()`. Vercel serves
concurrent requests from separate instances, so each also pays a full cold start: FastAPI import,
lifespan, Neon connect.

Measured on 2026-09-05 against `trader-ruddy.vercel.app`:

| Scenario | Per-request latency |
|---|---|
| Four concurrent, no cookie, warm instance | 4035 / 5751 / 8148 / 10399 ms |
| Sequential, cookie present, warm instance | 630 / 695 / 695 / 707 / 1264 ms |
| Four concurrent, no cookie, cold instance | four of five aborted at the client's 20s deadline |

The abort is `AbortSignal.timeout(DEFAULT_TIMEOUT_MS)` in `lib/api/client.ts` firing, which is
correct behaviour — it is the request underneath that should not take 20 seconds.

### Why it reads as a chart bug

An aborted `/api/watchlist` leaves `useWatchlistStore.status = "failed"` and `selectedTicker`
null, so `MainChart` renders "Pick a symbol from the watchlist to chart it." An aborted
`/api/portfolio/history` leaves `historyStatus = "failed"`, so `PnlChart` renders `LoadFailure`.
Two empty charts, intermittently, on first load only — which is exactly the report.

It also leaks three orphan guests per first visit: twelve rows each, expired eventually by the
cleanup cron, but wrong in the meantime and wrong in the row counts.

### The fix

In `lib/useAppBoot.ts`, await `loadSession()` before racing the other three:

```
// Caught, not awaited bare: a rejected session must not skip the fan-out.
await loadSession().catch(() => {})   // mints exactly one guest, sets the cookie
await Promise.allSettled([            // all three now carry it
  refreshPortfolio(), refreshWatchlist(), refreshChat(),
])
```

Both stages stay inside the existing `Promise.race` against `BOOT_MAX_MS`, so the cap still
bounds the boot screen and a hung session call still reveals the workspace. `loadSession` records
its own failure on the store, which is what the account control renders, so swallowing it here
loses nothing.

Nothing changes on the server. A server-side fix cannot help: separate lambda instances share no
memory, so there is nothing to deduplicate against.

## 4. The demo portfolio

### Holdings

Seeded at mint, alongside the existing watchlist and t=0 snapshot. Four positions, deliberately
two in profit and two at a loss so the heatmap has both colours to draw and the positions table
shows a signed value in each direction:

| Ticker | Quantity | Avg cost | Seed price | Cost basis |
|---|---|---|---|---|
| AAPL | 10 | 186.40 | 190.00 | 1,864.00 |
| MSFT | 4 | 428.00 | 420.00 | 1,712.00 |
| NVDA | 2 | 781.50 | 800.00 | 1,563.00 |
| TSLA | 3 | 254.00 | 250.00 | 762.00 |

Cash after seeding: `initial_cash - 5,901.00` = **4,099.00**. Every ticker is already in
`DEFAULT_WATCHLIST`, so the tracked-ticker union is unchanged and no reconcile behaviour differs.

### Backing trades

Each holding gets one `trades` row with `is_demo = TRUE`, timestamped over the preceding few
hours, so the History view of §7 has content on first load and the "trades are authoritative,
positions are a projection" invariant (D-21) is not violated by a position with nothing behind it.

### Backfilled snapshots

Forty `portfolio_snapshots` rows spread over the preceding six hours, valued by evaluating
`app.market.deterministic.price_at(ticker, t)` for each holding at each timestamp and adding the
cash. The function is a pure function of the clock, so on the serverless deployment — where it is
also the live price source — the backfilled curve joins the live one seamlessly.

On the container target the live source is the GBM simulator, whose path is generated in-process
and will not match. Both start from the same `SEED_PRICES`, so the curve is in the right place and
the join is not visible at chart scale. Marked with a `ponytail:` comment naming the ceiling; the
upgrade path is to have the simulator expose a `price_at`-shaped backfill of its own, which is not
worth doing for a demo seed.

### Seeding surface

`seed_user(db, settings, user_id, *, demo: bool = False)`.

- `UserStore.mint_guest()` passes `demo=settings.demo_portfolio`.
- `ResetService.reset()` passes `demo=(kind == "guest")` — a guest's reset restores the demo,
  because the demo *is* their seeded starting state; a signed-in user's reset returns them to a
  clean $10,000. The service is constructed with a `user_id` and no kind today, so it reads the
  kind inside its existing transaction rather than gaining a constructor argument that every
  caller would have to fetch.
- The existing idempotency guards stay. The snapshot insert's `WHERE NOT EXISTS` already prevents
  a re-seed from injecting a second t=0 point, and the demo backfill is guarded the same way.

New setting: `DEMO_PORTFOLIO` (`demo_portfolio: bool = True`), read through the existing
`_env_bool`. Setting it false restores today's behaviour exactly, which is what the E2E suite's
existing fresh-start assertions need.

## 5. Clearing the demo at sign-in

### The rule

On a completed OAuth callback resolving to `PROMOTE` or `CREATE`, clear the demo **only when both**
hold:

1. the session being promoted is a **guest** (or was just minted by `CREATE`), and
2. `has_activity(target_id)` is **false**.

Clearing means: delete the user's positions, trades and snapshots, restore `cash_balance` to
`initial_cash`, and write a fresh t=0 snapshot — the existing `ResetService` behaviour with
`demo=False`.

Condition 1 is not decoration. `PROMOTE` also fires when an **already signed-in user adds a second
provider**, and `decide()` reports `session_has_activity=False` for them because it only computes
that value for guests. Without the kind check, connecting a GitHub account to an existing Google
account would silently wipe a real portfolio. This is the single most dangerous line in the change
and gets its own test.

`SWITCH` clears nothing: the target is an existing account whose demo was already cleared when it
was first signed into, and the untouched guest row is left to expire on its own, exactly as today.

### Why `has_activity` needs a column

`has_activity()` counts trades, chat messages, and any divergence from the seeded watchlist. Demo
trades are trades, so seeding them would make every guest report `hasActivity: true`. Two things
break: the sign-in conflict dialog would fire on every sign-in — training people to dismiss the
one warning that matters — and this section's own condition 2 would never hold, so the demo would
never clear.

Migration 004, appended to `MIGRATIONS`:

```sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE
```

`has_activity`'s trades subquery gains `AND NOT is_demo`. The column is invisible above the
repository: `Trade` and the API responses are unchanged, and the History view shows demo trades
like any other, because they honestly describe how the positions came to be.

## 6. Navigation and layout

### Routes

```
app/(workspace)/layout.tsx      shell: Rail, Header, Footer, BootScreen,
                                ClaimConflictDialog, TradeReceiptDialog, ThemeSync,
                                usePriceStream(), useAppBoot(), the sessionVersion
                                and 15s revaluation effects
app/(workspace)/page.tsx        /            watchlist │ main chart + trade ticket │ assistant
app/(workspace)/portfolio/      /portfolio/  heatmap + performance, full-width positions
app/(workspace)/history/        /history/    trades table with realized P&L
app/privacy/page.tsx            unchanged — outside the group, and gets no stream
```

A route group leaves URLs untouched while giving the three workspace routes one shared layout
instance. `next/link` navigation between them therefore keeps a single `EventSource` open and the
lazily-imported chart bundles warm; the Zustand stores are module singletons, so nothing refetches
on a tab switch. This is what makes real routes affordable — a per-page shell would reconnect the
stream and re-download the chart bundle on every navigation.

`usePriceStream()` and `useAppBoot()` move out of `page.tsx` into the group layout. Both are
mount-only, and the layout mounts once.

### What each route holds

**`/` Overview.** Keeps the three-column shape, and the middle column drops to two rows: the main
chart and the trade ticket. The chart takes the space the heatmap, performance chart and positions
table used to compete for.

**`/portfolio/`.** The allocation heatmap and the performance chart side by side across the full
width, with the positions table full-width beneath them. No watchlist column and no assistant
column — the toolbar still carries the live total, so the numbers stay live.

**`/history/`.** The trades table, full width, from §7.

### The rail

Three `next/link` entries — Overview, Portfolio, History — replacing the four `getElementById`
scroll targets. The active route is marked with the systemBlue selection tint the watchlist rows
already use, and carries `aria-current="page"`.

The badges survive the change: Overview shows the watchlist count, Portfolio the position count,
History the trade count. The em-dash placeholder for "not known yet" stays, for the same reason it
exists today.

Below `lg` the rail keeps its horizontal icon-bar form. `components/layout/panels.ts` keeps both
its ids and its `minH` tokens: the ids stop being scroll targets but become the tour's targets
(§8) and the panels' section anchors, so the "both sides must agree on the spelling" reason the
file exists still holds. Its entries are re-keyed to the panels that survive on the overview, plus
the two that move.

### The backend catch-all

`/portfolio/` and `/history/` export as directories, which is the trap PLAN.md §11 records:
Vercel's CDN resolves a directory to its index without being asked, so a catch-all that only
matched files would look correct there and answer both routes with the trading workspace on the
container target alone. `app/main.py` already tries both spellings; the guard is
`TestExportedSubroutes` in `backend/tests/test_api.py`, which gains both routes.

## 7. `GET /api/portfolio/trades`

```
GET /api/portfolio/trades?limit=200
→ {"trades": [
     {"id", "ticker", "side", "quantity", "price", "executed_at",
      "value": 3498.00, "realized_pnl": 212.40}
   ]}
```

`limit` defaults to 200 and is capped at 500, matching how `/api/portfolio/history` bounds itself.
Newest first, which is what the table renders.

`value` is `round_cash(quantity * price)`. `realized_pnl` is `null` on every buy — not `0`, so the
table can print an em dash rather than a number that would read as "broke even".

### Realized P&L

Computed, never stored (D-57). A new pure function in `portfolio/formulas.py` replays the trade
log oldest-to-newest, carrying a running quantity and average cost per ticker, and uses the
existing `buy_avg_cost` and `realized_pnl` helpers so the arithmetic is the same one the trade
endpoint already performs:

```
replay_realized(trades: list[Trade]) -> dict[str, float | None]   # keyed by trade id
```

It must replay the **whole** log, not the page: a sell's basis depends on every buy before it, so
computing over a `limit`-truncated list would report the wrong number on the oldest sells shown.
The route therefore fetches the full log for the replay and slices afterwards. Bounded by the
retention the cleanup cron already applies; if the log ever outgrows that, the fix is a stored
basis, not a truncated replay.

A sell of a ticker with no prior buys — impossible through the service, which rejects short
selling, but reachable in a hand-edited database — yields `realized_pnl` against a zero basis
rather than raising. The route is a read; it does not get to fail because a row is odd.

## 8. The onboarding tour

`components/onboarding/Tour.tsx`. Rendered on `/` only, when `session.kind === "guest"` and
`localStorage["trader-tour-seen"]` is unset.

Five steps, each naming a target element by id: the watchlist, the main chart, the trade ticket,
the assistant, and the rail's Portfolio link. The spotlight is one absolutely-positioned rect
tracking `getBoundingClientRect()` on its target, with `box-shadow: 0 0 0 9999px` in the scrim
colour — no clip-path, no second overlay, no library. It re-measures on resize and on step change.

- Skip, Escape, and the final step's Done all dismiss and write the localStorage key.
- The key is written on dismissal only, so a visitor who reloads mid-tour sees it again — which is
  the behaviour you want while the tour is still the thing being evaluated.
- `prefers-reduced-motion` drops the transition between steps, consistent with the flash animation
  and the page-load reveal.
- Focus moves to the step's dialog on each advance; the dialog carries `role="dialog"` and
  `aria-modal="true"`, and the scrim is `aria-hidden`.
- A step whose target is missing — a narrow viewport where the rail has collapsed, say — is
  skipped rather than rendered against a zero rect.

A `localStorage` read that throws (private browsing) is caught and treated as "not seen", so the
tour shows. It is a first-run affordance, not state worth defending.

## 9. Testing

**Backend**
- `replay_realized` over a hand-built log: buy, buy, partial sell, full sell, re-buy. Asserts the
  basis carries across a full liquidation correctly.
- The demo seed writes four positions, four `is_demo` trades, and a backfilled snapshot series
  whose newest value is within a sensible band of cash plus holdings at seed prices.
- `has_activity()` is **false** for a freshly minted demo guest, and **true** after one real trade.
- A signed-in user adding a second provider keeps their positions. This is D-52's dangerous edge
  and the test that guards it.
- A guest with no activity signing in loses the demo and lands on a clean `initial_cash`.
- A guest who traded and then signs in keeps everything.
- `GET /api/portfolio/trades`: shape, ordering, the `limit` cap, `realized_pnl` null on buys, and
  that the replay is unaffected by `limit`.
- `TestExportedSubroutes` covers `/portfolio/` and `/history/` in both spellings.

**Frontend**
- `useAppBoot` calls `loadSession` before the other three, and still fans out when it rejects.
- The trades table: sign and arrow glyph on every realized value, an em dash on buys, the past
  tense on both sides.
- The tour: renders for a guest, not for a signed-in user, not once dismissed; Escape, Skip and
  Done each dismiss; a missing target is skipped.
- The rail marks the active route with `aria-current`.
- `theme.test.ts` gains any new foreground/background pairing the two new pages introduce, so the
  4.5:1 floor stays enforced rather than asserted.

**E2E**
- The existing fresh-start scenarios run with `DEMO_PORTFOLIO=false`, so their $10,000 and
  empty-positions assertions keep meaning what they meant.
- One new scenario with the demo on: first load shows four positions and a performance chart with
  points in it.

## 10. Documentation

PLAN.md is amended in the dated-note style the file already uses: §5 gains `DEMO_PORTFOLIO`, §7
gains the `is_demo` column and the demo seed, §8 gains `GET /api/portfolio/trades`, §10 is
rewritten for the three routes and the new panel inventory, and §11's directory-route section
names the two new routes. `planning/API_CONTRACT.md` gains the trades endpoint.

## 11. Out of scope

- Pagination beyond `limit` on the trades table. A demo account's log is small; a cursor is
  speculative until it isn't.
- Filtering or sorting the history view.
- A `/markets/` route. The watchlist and main chart stay on the overview, where the trade ticket
  needs them.
- Restoring the demo after it has been cleared. `POST /api/reset` on a signed-in account returns a
  clean $10,000, which is what a reset should mean once the account is real.
