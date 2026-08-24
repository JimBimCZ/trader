# Multi-user accounts, OAuth sign-in, and Postgres everywhere

**Date:** 2026-08-24
**Status:** Approved design, pending implementation plan
**Supersedes:** PLAN.md §2 ("No login, no signup"), §7 (SQLite), and the single-user
assumption throughout `DECISIONS.md`.

## 1. Motivation

Two changes, one dependent on the other.

Neon Postgres is already configured on the Vercel deployment. The adapter that uses it
(`backend/app/db/postgres.py`) has existed since the Vercel work but has never run against a real
instance, and the app has no way to tell two visitors apart — every browser shares the single
`users_profile` row keyed `"default"`. On a public URL that is not a demo, it is a shared bank
account.

This design makes each visitor their own user, lets them attach that identity to a Google or
GitHub account so it survives a change of browser, and drops SQLite so there is one database
engine rather than two schemas kept in sync by hand.

## 2. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D-1 | Guest by default, sign-in optional | Preserves the zero-friction first run PLAN.md §2 is built around, and keeps `docker compose up` working with no OAuth credentials |
| D-2 | On a sign-in collision the existing account wins; guest activity is discarded after confirmation | Predictable ("your account is your account") and avoids minting unlimited starting cash, which merging would allow |
| D-3 | Postgres everywhere; SQLite deleted | One schema, dev/prod parity, and no class of bug that appears only on Neon — the auth tables would otherwise double the dual-schema drift risk |
| D-4 | Guests expire after 7 days idle; signed-in accounts never expire | Bounds storage and the snapshot-writer loop on a public URL |
| D-5 | Per-request service construction (approach A) | Deleting the `user_id` default makes an unscoped query a construction error rather than a silent cross-user data leak |
| D-6 | Identities are never matched by email address | Cross-provider email matching is an account-takeover vector when a provider does not guarantee the address is verified |

## 3. Identity model

One row in `users_profile` per identity, discriminated by `kind`:

- **`guest`** — created on the first request arriving without a valid session cookie. Seeded with
  `initial_cash` and the ten default tickers, as `seed_if_empty` does today but per-user.
- **`user`** — has at least one row in `oauth_identities`. Never expires.

A guest is the same row with no identity attached, not a parallel code path. Signing in either
promotes that row in place or points the cookie at a different row. No other subsystem knows the
difference.

### Session

A stateless signed cookie. No session table.

- Name `trader_session`, payload `{uid}` signed with `SESSION_SECRET` (`itsdangerous`).
- The cookie carries the user id and nothing else. `kind` is deliberately *not* in it: promoting
  a guest in place would leave a stale value there, and the row is the only source of truth.
- `HttpOnly`, `SameSite=Lax`, `Secure` when not on localhost, `Max-Age` 90 days.
- `SameSite=Lax` is both required and sufficient: the OAuth callback is a top-level GET
  navigation, which Lax permits, while cross-site POSTs stay excluded.

**Accepted consequence.** There is no server-side revocation: "sign out everywhere" is not
possible, and rotating `SESSION_SECRET` signs out every user *and permanently orphans every guest
portfolio*. Both belong in the README. For a fake-money simulator this is the right trade against
a session table read on every request.

## 4. Schema

### Changes to `users_profile`

```sql
kind          TEXT NOT NULL DEFAULT 'guest' CHECK (kind IN ('guest','user'))
email         TEXT
display_name  TEXT
avatar_url    TEXT
last_seen_at  TEXT NOT NULL
```

### New table

```sql
CREATE TABLE IF NOT EXISTS oauth_identities (
    provider         TEXT NOT NULL,          -- 'google' | 'github'
    provider_user_id TEXT NOT NULL,
    user_id          TEXT NOT NULL REFERENCES users_profile(id) ON DELETE CASCADE,
    email            TEXT,
    linked_at        TEXT NOT NULL,
    PRIMARY KEY (provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_users_kind_seen ON users_profile (kind, last_seen_at);
```

### Foreign keys

All five per-user tables (`watchlist`, `positions`, `trades`, `portfolio_snapshots`,
`chat_messages`) gain `user_id TEXT NOT NULL REFERENCES users_profile(id) ON DELETE CASCADE`.
None exists today. This reduces guest expiry to a single `DELETE` and makes an orphaned row
unrepresentable.

### Migrations

`CREATE TABLE IF NOT EXISTS` cannot add a column to a table Neon already has. This is the gap
that bites on the *second* deploy, not the first.

An ordered, forward-only list of idempotent DDL statements (`ADD COLUMN IF NOT EXISTS`,
`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) runs at startup after
`initialize_schema`. No Alembic: the statements are idempotent, so the list needs no version
table and no down-migrations. A test runs the list twice and asserts the second run changes
nothing.

Adding the `NOT NULL` foreign keys to tables that may already hold rows requires the columns to
be backfilled first; the migration adds the constraint only after `UPDATE … SET user_id =
'default' WHERE user_id IS NULL`.

## 5. OAuth

Authlib on FastAPI. Sign-in is a full-page navigation (`<a href="/api/auth/login/google">`),
which is what makes it work from a static export — no popup, no `postMessage`, no Node runtime.

| Route | Purpose |
|---|---|
| `GET /api/auth/providers` | Which providers are configured, so the UI hides buttons it cannot fulfil |
| `GET /api/auth/login/{provider}` | Redirect to the provider; state and PKCE verifier in a short-lived signed cookie |
| `GET /api/auth/callback/{provider}` | Exchange the code, fetch userinfo, resolve identity, set the session cookie |
| `POST /api/auth/logout` | Clear the cookie; the next request mints a fresh guest |
| `GET /api/auth/me` | `{id, kind, email, name, avatar, has_activity}` |
| `POST /api/auth/claim` | Confirm a contested sign-in (§5.2) |

Every failure uses the existing error envelope from `backend/app/errors.py`. New codes:
`AUTH_PROVIDER_UNAVAILABLE` (404), `AUTH_STATE_INVALID` (400), `AUTH_EXCHANGE_FAILED` (502),
`CLAIM_TOKEN_INVALID` (400).

**PKCE state must live in a cookie, not process memory.** Serverless instances share nothing, so
an in-memory state store fails intermittently and unreproducibly. Starlette's cookie-backed
`SessionMiddleware`, keyed on the same `SESSION_SECRET`, satisfies this.

### 5.1 Identity resolution

```
identity = lookup(provider, provider_user_id)

identity exists?
├─ yes → target = identity.user_id           (D-2: existing account wins)
│         guest has activity? → do NOT switch; redirect to /?claim=conflict&token=…
│         guest untouched?    → switch the cookie silently
└─ no  → session is a guest? → promote in place: kind='user', attach profile, link identity
          otherwise          → create and seed a new user, link identity
```

"Has activity" means any trade, any watchlist mutation away from the seeded ten, or any chat
message. An untouched guest is the common case and must not produce a prompt.

### 5.2 The contested claim

The dialog fires only when a collision actually occurred, rather than warning before every
sign-in. The callback declines to switch the cookie and redirects with a short-lived signed token
naming the target user. The frontend shows the value at stake — "This Google account already has
a portfolio worth $12,431. Your guest activity will be discarded." — and `POST /api/auth/claim`
switches the cookie on confirmation. Cancelling leaves the guest session untouched.

One extra endpoint buys a prompt that is never a false alarm.

## 6. Request path

```
Request
 └─ current_user dependency
     ├─ valid cookie → load the row, touch last_seen_at (throttled to ~5 minutes)
     └─ no cookie    → INSERT a guest, seed it, set the cookie on the response
 └─ service factories build user-scoped repositories over the shared pool
```

`main.py`'s lifespan keeps only genuinely shared state: the connection pool, price cache, market
data source, history store, and reconciler. `TradeService`, `WatchlistService`, `ChatService`,
`ResetService`, and every repository move to per-request factories in `deps.py`.

`DEFAULT_USER_ID` and every `user_id: str = DEFAULT_USER_ID` parameter default are **deleted**.
That deletion is the mechanism behind D-5: after it, a repository constructed without a user does
not compile rather than quietly reading someone else's rows.

`GET /api/health` and `GET /api/stream/prices` are exempt from user resolution. Without the
exemption every crawler hit and every monitoring probe mints a guest row, and prices are not user
data.

Throttling `last_seen_at` matters: written on every request it turns each GET into a write, which
on Neon is a network round trip per read.

## 7. Shared subsystems

### 7.1 TickerReconciler — the correctness trap

`release_if_unheld()` currently asks whether *this* user still holds a ticker. With several users
that stops the price feed for a ticker another user is holding, and `reconcile.py`'s own
docstring names the consequence: valuation fails, or the position is silently valued at zero.

Both sides become global:

- `compute_tracked_tickers()` returns `DISTINCT ticker` across all watchlists ∪ all positions
  with `quantity > EPSILON`. Expired guests are deleted rows, so they drop out of this query on
  their own — no liveness filter is needed here.
- `release_if_unheld()` releases only when *no* user watches or holds the ticker.

The per-user watchlist cap stays at 25, reported as `WATCHLIST_FULL`. A new global tracked cap
(100) bounds simulator and Massive polling cost, and needs its own code — `MARKET_CAPACITY_FULL`
(503). Reporting a global limit as `WATCHLIST_FULL` would tell a user their own watchlist is
full when it holds three tickers.

### 7.2 SnapshotWriter

The container task iterates users seen within the last hour rather than every user.

The serverless path currently writes a snapshot from the SSE heartbeat, which no longer works
because the stream has no user to attribute a snapshot to. It is replaced by writing a snapshot
during `GET /api/portfolio` when the newest one is older than `snapshot_interval_seconds`. This
is naturally scoped to active users and lets the heartbeat plumbing in `create_stream_router` and
`write_snapshot_from_stream` be deleted.

### 7.3 ResetService

Scoped to the calling user; it must not touch other users' rows. It then triggers a global
reconcile, because the tickers it released may still be held by others.

### 7.4 Guest cleanup

Deletes `kind='guest' AND last_seen_at < now - GUEST_TTL_DAYS`; the cascades of §4 remove
everything else. A daily background task in the container; on Vercel, `POST /api/admin/cleanup`
guarded by `CLEANUP_SECRET` and driven by a Vercel Cron entry in `vercel.json`.

## 8. Postgres everywhere

Deleted: `SqliteDatabase`, `open_connection`, `SCHEMA_SQL`, the `aiosqlite` dependency,
`Settings.db_path`, the `DB_PATH` variable, and `_default_db_path()`'s `/tmp/trader.db` fallback.
With one implementation remaining, the `Database` ABC and its `sequence_column` indirection
collapse into `PostgresDatabase`, where `seq` is always the tiebreaker.

`_to_numbered()` — the `?` → `$1` rewriter — is **kept**. It is legacy once SQLite is gone, but
hand-converting roughly forty queries to `$n` is churn with real typo risk and no behavioural
gain. It stays documented as a deliberate convenience rather than as an abstraction boundary.

`docker-compose.yml` gains a `postgres:16` service with a healthcheck and a named volume; the app
service waits for it to report healthy. The start/stop scripts wrap compose and need no change.

`DATABASE_URL` becomes **required**. Losing the `/tmp` fallback means a misconfigured deploy fails
loudly at startup instead of silently serving a portfolio that evaporates on the next cold start.

**Accepted cost:** the quick start now needs a second container, and offline use needs it running.

## 9. Frontend

Static export throughout (`output: "export"` in `next.config.ts` rules out NextAuth/Auth.js;
auth lives in FastAPI, which also keeps Docker and Vercel identical).

- `useSessionStore` fetches `/api/auth/me` on mount.
- Toolbar: avatar and a menu containing Sign out when signed in; a Sign in button opening a sheet
  with the configured providers when a guest, plus an unobtrusive "browsing as a guest — sign in
  to keep this portfolio" line.
- The claim-conflict dialog renders on `?claim=conflict`.
- After sign-out or a claim, a `sessionVersion` bump forces every store to refetch: the portfolio
  behind the same URL now belongs to a different identity.

All of it stays inside the Apple language of PLAN.md §2 and §10 — system materials, systemBlue as
the only interaction colour, no new palette tokens, and provider buttons in the neutral fill
rather than Google or GitHub brand colours. New foreground/background pairings go into
`__tests__/lib/theme.test.ts` like every other pairing, so the 4.5:1 floor stays enforced by test.

## 10. Configuration

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | **yes** | — | Postgres connection string; startup fails without it |
| `SESSION_SECRET` | **yes** | — | Cookie signing. Generated ephemerally in local dev with a loud warning |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | no | — | Absent → button hidden, login route 404s |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | no | — | Same |
| `PUBLIC_BASE_URL` | on Vercel | request origin | Callback URL construction. Falls back to the
`X-Forwarded-Proto`/`X-Forwarded-Host` pair, then to the request URL; set it explicitly wherever a
proxy rewrites the host, because a wrong value silently breaks the OAuth redirect |
| `GUEST_TTL_DAYS` | no | `7` | Idle expiry window for guests |
| `CLEANUP_SECRET` | no | — | Guards the cron cleanup endpoint |
| `AUTH_MOCK` | no | `false` | Enables `/api/auth/dev-login/{id}` for E2E only |

Providers being optional is what keeps the quick start zero-config: with no credentials the app
delivers the guest experience, which is exactly today's behaviour.

## 11. Testing

Fourteen of twenty-seven backend test files build on `SqliteDatabase(tmp_path)`, so the fixture
change is the bulk of the work.

- The `db` fixture connects to `TEST_DATABASE_URL` and gives each test an isolated schema
  (`CREATE SCHEMA test_<uuid>` plus `search_path`). Far cheaper than a container or a database per
  test, and safe under `pytest-xdist`.
- The CI backend job gains a `services: postgres:16` container.
- New coverage: cookie signing, verification, and tamper rejection; guest minting and its
  idempotency; the full identity-resolution matrix of §5.1; **cross-user isolation** — user A's
  requests can neither read nor mutate user B's rows, the highest-value test in the suite;
  expiry and its cascades; the reconciler union and release rules across users; the migration list
  run twice.
- E2E largely survives: the guest path needs no OAuth credentials, so the existing Playwright
  suite runs unchanged. Sign-in scenarios use the `AUTH_MOCK`-gated `dev-login` route, which is
  refused unless that variable is set.

## 12. Out of scope

Email/password authentication. Account deletion UI. Cross-provider email linking (D-6). Anything
social: leaderboards, shared or public portfolios, following other users.

**Known consequence.** The existing `"default"` row on Neon becomes an orphan guest that no
cookie points at, and expires after seven days. Nothing of value is lost — the deployment's state
has been ephemeral since it went up.

## 13. Suggested build order

The three parts are separable, and each leaves the app working:

1. **Postgres everywhere** (§8) plus the migration runner (§4). No behaviour change — still one
   shared user. This is the riskiest step for the existing test suite and the cheapest to verify,
   so it goes first and alone.
2. **Per-user scoping** (§6, §7). Delete `DEFAULT_USER_ID`, move service construction per-request,
   fix the reconciler and snapshot writer. Guests are minted from cookies; there is still no way
   to sign in. The app is fully multi-user at this point.
3. **OAuth and the frontend** (§5, §9). Identity linking, the claim flow, and the toolbar UI.

Step 2 is where the cross-user isolation tests land, and they should be written before the
scoping change rather than after it.
