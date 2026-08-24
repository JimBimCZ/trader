# Vercel Deployment — Plan

*Written 2026-08-24. The Docker path in PLAN.md §11 is unchanged and stays the reference
deployment; this document describes a second target that runs the same application on Vercel's
serverless platform.*

## Why the app does not fit Vercel as built

`backend/app/main.py` builds a long-lived process. Its `lifespan` starts three background
tasks — the 500 ms GBM simulator writing into an in-memory `PriceCache`, the history ring-buffer
collector, and the 30 s snapshot writer — and opens one `aiosqlite` connection to a file on disk.
SSE readers stream off the shared in-memory cache.

Vercel gives none of that: invocations are stateless, there is no writable persistent disk, no
work runs between requests, and a function has a bounded lifetime. Three of the four subsystems
have to change; the routes, services, repositories and the entire frontend do not.

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

### 2. SQLite → Neon Postgres

`Database` becomes an interface with two implementations, chosen by whether `DATABASE_URL` is set.
Where it is not, SQLite falls back to `/tmp/trader.db` — the one writable path a function has. That
keeps a deployment working before the database exists, at the cost of state that belongs to a
single instance and dies with it. `/api/health` reports which one is live.

- `PostgresDatabase` translates `?` placeholders to `$n`, so **every repository's SQL is reused
  verbatim**. Only three things genuinely differ: `REAL` → `DOUBLE PRECISION`, `rowid` tiebreaks
  → a `seq BIGSERIAL` column, and `executescript` → a single `execute`.
- The per-process `asyncio.Lock` guarding trade atomicity is meaningless across instances and is
  replaced by `pg_advisory_xact_lock` inside the transaction.
- Neon's **pooled** endpoint is required, which means `statement_cache_size=0` — pgbouncer in
  transaction mode breaks asyncpg's prepared statements.

### 3. Background tasks go away

| Task | Replacement |
|---|---|
| Simulator loop | Deleted. Prices are computed, not ticked. |
| History collector | Deleted. History is computed backwards from now. |
| Snapshot writer | Moves into the SSE generator: one snapshot per 30 s of stream time. Trades already write their own. |

The snapshot writer belongs in the stream because that is precisely when a user is watching —
which is the only time the P&L chart is read.

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

## Deploying

The project builds from the repository root. Vercel runs the frontend build and serves
`frontend/out` from the CDN; `api/index.py` becomes the one Python function, and `vercel.json`'s
rewrite is what sends `/api/*` to it and nothing else.

```
vercel.json        build, rewrite, function limits, non-secret env
requirements.txt   the function's dependencies — deliberately not the backend's full set
api/index.py       puts backend/ on the import path and exposes app.main:app
```

### Environment

| Variable | Set where | Notes |
|---|---|---|
| `VERCEL` | automatic | Selects the computed market source and the `/tmp` database path. |
| `LLM_MOCK` | `vercel.json` | `true`. The assistant answers deterministically and costs nothing. |
| `STREAM_MAX_SECONDS` | `vercel.json` | `55`, just under the 60 s function limit, so the stream closes itself. |
| `DATABASE_URL` | dashboard | Neon's **pooled** URI. Absent, the app runs on ephemeral `/tmp` SQLite. |

### Finishing the setup

1. **Add Postgres.** Vercel dashboard → Storage → Marketplace → Neon (free tier). Copy the pooled
   connection string — the host contains `-pooler` — into `DATABASE_URL` and redeploy. Confirm with
   `curl https://<app>/api/health`.
2. **Add the real assistant**, if wanted. Put `litellm` in `requirements.txt` and
   `OPENROUTER_API_KEY` in the dashboard, and drop `LLM_MOCK` from `vercel.json`. It adds ~130 MB to
   the bundle and a real cost per message, on an app that has no authentication.

### What this deployment does not carry

`MASSIVE_API_KEY` is ignored — the Massive client is not installed, so real market data stays a
container-only feature. Neither is numpy, so the stateful GBM simulator cannot be selected here
either; `MARKET_SOURCE` is `deterministic` and forcing it back would fail on import.
