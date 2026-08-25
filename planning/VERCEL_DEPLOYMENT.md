# Vercel Deployment — Plan

*Written 2026-08-24, updated the same day once the "postgres-everywhere" phase landed
(`docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md`). The Docker path in
PLAN.md §11 is unchanged and stays the reference deployment; this document describes a second
target that runs the same application on Vercel's serverless platform.*

*What changed underneath this doc: when it was first written, "SQLite → Neon Postgres" (§2 below)
was a Vercel-specific adaptation — the Docker target still ran SQLite, and a missing
`DATABASE_URL` fell back to an ephemeral `/tmp` SQLite file so a fresh Vercel deploy would still
boot. The postgres-everywhere phase deleted SQLite and the `/tmp` fallback entirely: every target,
Docker included, now requires Postgres via `DATABASE_URL`, and there is no fallback if it is
absent. §2 is kept, updated, because the mechanics it describes (placeholder translation, the
advisory lock, the pooled-endpoint requirement) are still exactly how the app talks to Postgres —
it is just no longer a Vercel-only concern.*

## Why the app does not fit Vercel as built

`backend/app/main.py` builds a long-lived process. Its `lifespan` starts three background
tasks — the 500 ms GBM simulator writing into an in-memory `PriceCache`, the history ring-buffer
collector, and the 30 s snapshot writer. SSE readers stream off the shared in-memory cache.

Vercel gives none of that: invocations are stateless, there is no writable persistent disk, no
work runs between requests, and a function has a bounded lifetime. The simulator and the snapshot
writer have to change (§1 and §3), and serving is split between the CDN and one function (§4); the
routes, services, repositories and the entire frontend do not. The database (§2) no longer needs
Vercel-specific adaptation — Postgres, via `DATABASE_URL`, is what every target requires now.

## The four changes

### 1. Market data becomes a pure function of time

The stateful random walk is replaced by `price(ticker, t)` — deterministic, so every instance,
every SSE connection and every request agrees exactly without sharing anything.

- **Session** = one UTC day. `W(0) = 0` at UTC midnight, so the seed price *is* the session open
  and `daily_change_percent` is exact. No cross-day chaining, no drift away from realistic prices.
- **The walk** is standard Brownian motion built by **Lévy construction** (a Brownian bridge
  descended by binary subdivision). Each node's normal is drawn from `blake2b(seed, key…)`, so
  `W(τ)` is evaluable at arbitrary τ in ~20 hashes instead of by replaying 172 800 ticks.
- **Correlation** comes from a two-factor decomposition rather than a Cholesky factorisation:
  `W_i = √0.3·M + √(ρ_i−0.3)·S_sector + √(1−ρ_i)·I_i`. That reproduces the documented matrix
  exactly — 0.6 within tech, 0.5 within finance, 0.3 cross-sector and for TSLA — with unit
  variance and no matrix algebra, so **numpy is no longer needed**.
- **Prices** are still GBM: `S₀·exp((μ − σ²/2)·τ + σ·W(τ))`, τ measured in trading years off the
  same `TRADING_SECONDS_PER_YEAR` constant, with the same per-ticker μ/σ from `seed_prices.py`.
- **Events** (the 2–5 % drama shocks) survive as a per-minute lottery, but *decay* over ~5 minutes
  rather than persisting. The shipped simulator multiplies the price permanently, which is harmless
  over the few minutes anyone watches it and compounds into a second, louder random walk over a
  full session — 144 shocks a day, whose variance buries the GBM and, being drawn per ticker,
  flattens every correlation to zero. Measured: 0.44 session volatility against an intended 0.027.

Integration is deliberately small: `DeterministicPriceCache` and `DeterministicHistoryStore`
subclass the existing `PriceCache` / `HistoryStore` and compute on read. Every consumer — SSE,
trade pricing, portfolio valuation, `/api/health`, `/api/history` — is untouched.

The existing GBM simulator stays exactly as it is and remains the Docker default. Selection is by
`MARKET_SOURCE`, defaulting to `deterministic` when `VERCEL` is set.

### 2. Postgres, required on every target

*Originally this section was the Vercel-specific half of a dual-backend `Database`: SQLite locally,
Postgres (falling back to ephemeral `/tmp/trader.db` if `DATABASE_URL` was unset) on Vercel. The
postgres-everywhere phase deleted SQLite, `SqliteDatabase`, and the `/tmp` fallback outright —
`Database` is now simply `PostgresDatabase`, required everywhere, and `Settings.require_database_url()`
raises `ConfigurationError` at startup if `DATABASE_URL` is absent. Nothing below is Vercel-specific
any more; it is just how the app talks to its one database.*

- `PostgresDatabase` translates `?` placeholders to `$n`, so **every repository's SQL stays
  written the same way** it always has been. `REAL` maps to `DOUBLE PRECISION`, and every table
  that needs one carries an explicit `seq BIGSERIAL` column as its ordering tiebreaker — there is
  no more `sequence_column` indirection to pick between a SQLite `rowid` and a Postgres sequence,
  because there is only one backend.
- `Database.transaction()` takes a Postgres `pg_advisory_xact_lock` for its duration, on top of
  the in-process `asyncio.Lock` (`trade_lock`/`watchlist_lock`, created once in `main.py`'s
  lifespan) the services already hold. The in-process lock only ever saw one process; the
  advisory lock is what makes that guarantee hold across every instance too — the case Vercel
  actually creates, by happily starting more than one concurrent invocation, each with its own
  separate lock object that cannot see the others.
- A **pooled** endpoint is required wherever the database is Neon, which means
  `statement_cache_size=0` — pgbouncer in transaction mode breaks asyncpg's prepared statements.
  The local Docker Postgres is unpooled and does not need this, but the setting is harmless there.
- A forward-only, idempotent migration runner (`app/db/migrations.py`) now runs after `init_db` and
  `seed_if_empty` on every startup, on every target. Migration 001 attaches every per-user table to
  `users_profile` with `ON DELETE CASCADE`.

### 3. Background tasks go away

*Updated 2026-08-25, once the per-user-scoping phase landed: the snapshot writer no longer rides
the SSE heartbeat described in the original version of this row — that plumbing (a snapshot tick
inside the SSE generator) was deleted outright, because the SSE stream never resolves a caller
(`GET /api/stream/prices` is one of the two routes that never mints a session — see
`planning/API_CONTRACT.md` §0) and so has no single user to attribute a snapshot to any more. See
`docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md`.*

| Task | Replacement |
|---|---|
| Simulator loop | Deleted. Prices are computed, not ticked. |
| History collector | Deleted. History is computed backwards from now. |
| Snapshot writer | `GET /api/portfolio` calls `TradeService.write_snapshot_if_stale()`, which writes a snapshot for the calling user only when their newest one is already older than `snapshot_interval_seconds` (30s default). Trades still write their own snapshot inline, as they always have. This reuses exactly the read that is naturally scoped to a user who is actually looking at the app — the same principle the deleted SSE-heartbeat approach was reaching for, without needing a stream to hang it off. |
| Guest cleanup | Deleted as a background task on this target (nothing runs between requests to drive a loop). `vercel.json` schedules a daily `GET /api/admin/cleanup` hit at `0 4 * * *` (04:00 UTC) instead. **This does not yet work end-to-end**: the route requires an `X-Cleanup-Secret` header (`planning/API_CONTRACT.md` §8), but a `vercel.json` `crons` entry takes only `path` and `schedule` — there is no way to attach a custom header to it. Vercel's own convention for a secured cron target is a `CRON_SECRET` env var it auto-injects as `Authorization: Bearer <CRON_SECRET>` (confirmed against Vercel's current docs), which is *not* what this route checks. So, as configured, the daily Cron hit arrives with no `X-Cleanup-Secret` and is rejected with `CLEANUP_FORBIDDEN` exactly like any other unauthenticated call — idle guests are not actually expired on this target yet. `CLEANUP_SECRET` today only makes the route reachable by a manual/curl call that sets the header by hand. Closing this gap (switching the check to `CRON_SECRET`/`Authorization`, or fronting the Cron hit some other way) is unresolved. |

The container target keeps both as real background tasks: `SnapshotWriter` ticks every 30s and
writes one snapshot per user active in the last hour; `GuestCleaner` runs once a day in-process.
Only the serverless target needs the per-request / Cron substitutes above.

### 4. Serving layout

Static export on the CDN, FastAPI as one Python function; no static asset is served through
Python.

```
/            → frontend/out           (Vercel CDN)
/api/*       → api/index.py           (FastAPI, rewritten from /api/(.*))
```

`litellm` (91 MB, ~130 MB with its tree) and `numpy` (26 MB) drop out of the Vercel bundle — their
imports become lazy, so the modules stay importable without them. Deploying with `LLM_MOCK=true`
therefore ships ~15 MB of dependencies instead of ~160 MB.

## Known trade-offs

- **SSE reconnects** every time the function hits `maxDuration` (60 s on Hobby). `EventSource`
  already retries on the server's `retry: 1000` directive, so this is invisible — but streaming
  is billed for its whole duration, and an idle open tab bills continuously.
- **Prices reset to seed at UTC midnight.** Accepted: it keeps prices realistic and makes the
  session baseline exact.
- **The AI chat ships mocked.** Adding `OPENROUTER_API_KEY` alone is not enough; `litellm` must
  also be added back to `requirements.txt`.
- **Idle guests are not actually expired on this target yet.** `vercel.json`'s Cron entry hits
  `GET /api/admin/cleanup` daily, but the route requires an `X-Cleanup-Secret` header and a
  `crons` entry has no way to attach one — see §3. Unresolved.

## Deploying

The project builds from the repository root. Vercel runs the frontend build and serves
`frontend/out` from the CDN; `api/index.py` becomes the one Python function, and `vercel.json`'s
rewrite is what sends `/api/*` to it and nothing else.

```
vercel.json        build, rewrite, function limits, non-secret env, and the daily
                    guest-cleanup Cron entry (`0 4 * * *` → `GET /api/admin/cleanup`,
                    though see §3's note: it cannot yet authenticate itself)
requirements.txt   the function's dependencies — deliberately not the backend's full set
api/index.py       puts backend/ on the import path and exposes app.main:app
```

### Environment

| Variable | Set where | Notes |
|---|---|---|
| `VERCEL` | automatic | Selects the computed market source. |
| `LLM_MOCK` | `vercel.json` | `true`. The assistant answers deterministically and costs nothing. |
| `STREAM_MAX_SECONDS` | `vercel.json` | `55`, just under the 60 s function limit, so the stream closes itself. |
| `DATABASE_URL` | dashboard | Neon's **pooled** URI. **Required** — there is no fallback any more; absent, the function raises `ConfigurationError` on cold start instead of running on ephemeral storage. |
| `SESSION_SECRET` | dashboard | Signs the `trader_session` cookie. Every cold start with it unset generates a fresh one, which invalidates every existing cookie and permanently orphans every guest's portfolio — the row survives in Neon, but nothing can prove which cookie pointed at it. On a platform that recycles instances constantly, leaving this unset is worse here than on a long-lived container. Set it once, in the dashboard, before real use. |
| `GUEST_TTL_DAYS` | dashboard (optional) | Days of inactivity before a guest is deleted (default 7). Read by the Cron-driven cleanup route, same as on the container target. |
| `CLEANUP_SECRET` | dashboard | Guards `GET`/`POST /api/admin/cleanup` (`X-Cleanup-Secret` header). Set or not, **the scheduled Cron hit itself cannot supply this header today** — see the Guest cleanup row above — so on this target it currently only enables a manual/curl call, not the automated one `vercel.json` schedules. |

### Finishing the setup

1. **Add Postgres.** Vercel dashboard → Storage → Marketplace → Neon (free tier). Copy the pooled
   connection string — the host contains `-pooler` — into `DATABASE_URL` and redeploy. This step is
   no longer optional: without it the deployment does not come up at all, rather than degrading to
   ephemeral `/tmp` storage as it did before the postgres-everywhere phase. Confirm with
   `curl https://<app>/api/health`.
2. **Add the real assistant**, if wanted. Put `litellm` in `requirements.txt` and
   `OPENROUTER_API_KEY` in the dashboard, and drop `LLM_MOCK` from `vercel.json`. It adds ~130 MB to
   the bundle and a real cost per message, on an app that has no authentication.

### Access and cost

The production domain is public: Vercel Authentication cannot cover it on the Hobby plan, which
refuses `ssoProtection` for production outright. Preview deployments and production *deployment*
URLs are gated by it; the production domain is not, and password protection is paid too. The app
has no sign-in of its own, so anyone with the URL is minted their own anonymous guest and can trade
that guest's imaginary money — isolated from every other guest's, but not gated behind anything.

The cost that matters is the price stream. An open tab holds an SSE connection, and streaming is
billed for its whole duration — `STREAM_MAX_SECONDS` closes it at 55 s but `EventSource`
reconnects, so an idle tab bills continuously. A usage limit on the account is what bounds that:
Hobby pauses the project rather than charging. The alternative is pausing the project between
demos.

### What this deployment does not carry

`MASSIVE_API_KEY` is ignored — the Massive client is not installed, so real market data stays a
container-only feature. Neither is numpy, so the stateful GBM simulator cannot be selected here
either; `MARKET_SOURCE` is `deterministic` and forcing it back would fail on import.
