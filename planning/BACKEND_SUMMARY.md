# Backend — Component Summary

Status: **complete**. 314 tests, 97% coverage, ruff clean.

## Structure

```
backend/app/
├── main.py            composition root: create_app() + lifespan
├── config.py          Settings, read once from the environment
├── clock.py           the single time seam (patched by tests)
├── errors.py          AppError hierarchy + the JSON error envelope
├── deps.py            FastAPI dependencies, resolved from app.state
├── reconcile.py       owns the tracked-ticker set
├── db/                schema, connection, seed
├── market/            (pre-existing) simulator, Massive, cache, SSE
├── portfolio/         models, formulas, repository, service, snapshots, router
├── watchlist/         repository, service, router
├── history/           ring buffer, collector, router
├── llm/               models, prompt, client, mock, executor, service, router
└── system/            health, reset
```

Every domain follows repository → service → router. Business logic lives in the service; the
repository holds SQL; the router only translates HTTP.

## The decisions that shaped it

**Tracked tickers are `union(watchlist, open positions)`.** `reconcile.py` is the only module
allowed to call `source.remove_ticker()`, because that call also evicts the cached price. Removing
a ticker the user still holds would leave the position unpriceable.

**A missing price is an error, never zero.** `formulas.total_value()` raises rather than valuing an
unpriced holding at nothing, which would quietly write a wrong number into the P&L history.

**Trades hold a lock across the whole transaction.** aiosqlite serializes individual statements,
but a trade is read-validate-write with `await` points in between. Without the lock two concurrent
trades interleave and lose an update, and a second `BEGIN IMMEDIATE` on the shared connection
fails outright. `tests/portfolio/test_service.py::TestConcurrency` runs ten parallel buys and
asserts all ten land.

**The database is initialized in the lifespan, not on first request.** The market source needs the
watchlist to know what to track, so it cannot wait for a request. This resolves the contradiction
`REVIEW.md` B.3.1 identified.

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
