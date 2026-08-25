# Backend — Component Summary

Status: **complete**. Ruff clean. Runs on Postgres only — SQLite was removed
2026-08-24; see `docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md`. The app is
now multi-user (anonymous guests, no sign-in yet) — see `docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md` and the "Per-request services" section below.

## Structure

```
backend/app/
├── main.py            composition root: create_app() + lifespan
├── config.py          Settings, read once from the environment
├── clock.py           the single time seam (patched by tests)
├── errors.py          AppError hierarchy + the JSON error envelope
├── deps.py            FastAPI dependencies: resolves the caller from the session
│                       cookie, then builds each service per request, scoped to that user
├── identity/          the signed session cookie, and the user store (mint/load/touch/expire)
├── reconcile.py       owns the tracked-ticker set, globally across every user
├── db/                Postgres connection, schema, per-user seed, migrations
├── market/            (pre-existing) simulator, Massive, cache, SSE
├── portfolio/         models, formulas, repository, service, snapshots, router
├── watchlist/         repository, service, router
├── history/           ring buffer, collector, router
├── llm/               models, prompt, client, mock, executor, service, router
└── system/            health, reset, guest cleanup
```

Every domain follows repository → service → router. Business logic lives in the service; the
repository holds SQL; the router only translates HTTP.

## Per-request services

Services used to be built once in the lifespan, against a single hardcoded `DEFAULT_USER_ID`.
`DEFAULT_USER_ID` is gone; every repository constructor now takes a required `user_id`, and
there is no default to fall back on. `app/deps.py`'s `get_current_user` resolves the caller from
the `trader_session` cookie on every request — minting and seeding a fresh guest the first time a
browser arrives without one — and each `get_*_service` dependency then builds a fresh
`TradeService` / `WatchlistService` / `ChatService` / `ResetService` scoped to that one user id.
What stays shared, off `app.state`, built once in the lifespan: the connection pool, the price
cache, the market source, the ticker reconciler, and the two `asyncio.Lock`s that order concurrent
writes within one process. Only the repositories are per-user; everything they read or write
through is shared infrastructure.

Two background tasks that used to serve one implicit user now iterate every user the store
reports active in the last hour: `SnapshotWriter` (writes one portfolio snapshot per active user
per interval) and `GuestCleaner` (deletes guests idle past `GUEST_TTL_DAYS`, container target
only — see `planning/VERCEL_DEPLOYMENT.md` for the Vercel Cron equivalent).

## The decisions that shaped it

**Tracked tickers are `union(watchlist, open positions)`, computed globally across every user, not
per caller** — the tracked set feeds one shared price cache, so "should we track this?" is a
question about every user at once. `reconcile.py` is the only module allowed to call
`source.remove_ticker()`, because that call also evicts the cached price; it only releases a
ticker once no user anywhere still watches or holds it.

**A missing price is an error, never zero.** `formulas.total_value()` raises rather than valuing an
unpriced holding at nothing, which would quietly write a wrong number into the P&L history.

**Trades hold a lock across the whole transaction.** A trade is read-validate-write with `await`
points in between; without serialization two concurrent trades can interleave and lose an update.
`Database.transaction()` (`postgres.py`) takes a Postgres transaction-scoped advisory lock
(`pg_advisory_xact_lock`) for the duration, so writes are serialized across every connection in the
pool, not just within one process. `tests/portfolio/test_service.py::TestConcurrency` runs ten
parallel buys and asserts all ten land.

**The database is initialized in the lifespan, not on first request.** The market source needs the
tracked-ticker union to know what to track, so it cannot wait for a request. Startup order is
`init_db` -> `run_migrations`, then the global tracked-ticker union is computed and the market
source starts. This resolves the contradiction `REVIEW.md` B.3.1 identified.
`seed_if_empty` is gone: there is no single user to seed at startup any more, so a fresh database
starts with no users at all. Each guest is seeded individually, in the same transaction as its
`users_profile` row, the moment `UserStore.mint_guest()` creates it — see `app/identity/store.py`.

**Postgres is required, not optional.** `DATABASE_URL` must be set; `Settings.require_database_url()`
raises `ConfigurationError` at startup otherwise. There is no file-based fallback — the one it
replaced (SQLite locally, `/tmp` on Vercel) worked until an instance recycled and then silently
lost the portfolio, which is worse than refusing to start.

**`trades` is authoritative; positions and cash are a projection.** The execution algorithm is
exactly the replay procedure, so a future "recompute from trades" repair is well defined.

**Chat failures are not HTTP failures.** `POST /api/chat` returns 200 with `error: true` when the
model is unreachable, so the chat panel needs no separate error path.

## Verified, not assumed

Structured outputs were confirmed working on the `openrouter/openai/gpt-oss-120b` + Cerebras path
with a real call before the chat feature was built on them (`DECISIONS.md` D-29). The
parse-and-repair retry remains as a fallback.

## Where to look first

| Question | File |
|---|---|
| What does the API return? | `planning/API_CONTRACT.md` |
| How does a trade execute? | `app/portfolio/service.py` |
| Why is this ticker still streaming? | `app/reconcile.py` |
| What does the LLM see? | `app/llm/prompt.py` |
| What happens on startup? | `app/main.py` lifespan |
