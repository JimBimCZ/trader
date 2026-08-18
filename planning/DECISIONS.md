# DECISIONS.md — Resolved Design Decisions

Status: **authoritative**. Where this file and `PLAN.md` disagree, this file wins.

This log resolves the open items raised in `PLAN.md` §13 and `REVIEW.md`. Each entry states the
decision, the source item, and the rationale where it is not obvious. Items are grouped by area,
not by original numbering; the `§13 #n` / `REVIEW B.n` references let you trace back.

---

## 1. Document hierarchy

| Rank | Document | Role |
|---|---|---|
| 1 | `planning/API_CONTRACT.md` | Wire format. Frozen. The single file the frontend builds against. |
| 2 | `planning/DECISIONS.md` (this file) | Resolved policy. Supersedes PLAN.md prose. |
| 3 | `planning/PLAN.md` §1–§12 | Product brief and vision. |
| 4 | `planning/REVIEW.md`, `PLAN.md` §13 | Historical review passes. Retained for provenance; no longer open questions. |
| 5 | `planning/archive/*` | Working docs for the completed market-data component. |

Shipped code beats all documents. Where a doc describes behavior the code does not have, the doc is
wrong until the code changes.

---

## 2. Market data and the tracked-ticker set

**D-01 — The price source tracks `union(watchlist tickers, tickers with a non-zero position)`.**
(§13 #5) One reconciliation helper owns this set. It is recomputed on startup and after every
watchlist or position mutation.

**D-02 — Removing a watched ticker you still hold is allowed, and does not stop its price feed.**
(§13 #6) The delete removes the watchlist row only. Because of D-01 the ticker stays in the price
source while a position remains.

**D-03 — `source.remove_ticker()` may only be called for tickers with no open position.**
(REVIEW B.2.4) `remove_ticker()` also evicts the cached price. Calling it on a held ticker makes
`get_price()` return `None` and silently corrupts portfolio valuation.

**D-04 — Portfolio valuation treats a missing cached price as an error, never as 0.**
(REVIEW B.2.4) A position with no price is surfaced as an error, not valued at zero. Zero valuation
would tank the P&L chart and the heatmap with no visible cause.

**D-05 — Trading an unwatched ticker auto-adds it to the watchlist and the price source.**
(§13 #7) Rejecting the trade is the more defensible API, but this is a demo where the LLM names
tickers conversationally; auto-add is the behavior a user expects. The trade then blocks until a
price is cached (see D-19).

**D-06 — Ticker canonicalization is `ticker.strip().upper()`, applied in one shared helper.**
(§13 #10, REVIEW B.2.3) The helper is used by the REST routes, the LLM action executor, the seed
data, and — as defence in depth — inside both `MarketDataSource` implementations. The existing
inconsistency (Massive normalizes, the simulator does not) is a real bug: `add_ticker("aapl")` in
simulator mode creates a second instrument alongside `AAPL`.

**D-07 — Ticker validation: `^[A-Z]{1,5}$` after canonicalization.**
(§13 #8) Anything else is rejected with `INVALID_TICKER`. In simulator mode a valid-but-unknown
symbol gets a synthetic seed price (the simulator already does this: `random.uniform(50, 300)`).
In Massive mode an unknown symbol simply never receives a price, and any trade against it fails
with `PRICE_UNAVAILABLE`.

**D-08 — Watchlist cap: 25 tickers.** (§13 #9) Exceeding it returns `WATCHLIST_FULL`. This keeps
Massive's grouped snapshot call within free-tier limits and bounds the SSE payload size.

**D-09 — `session_open` is added to the price payload.**
(§13 #11, REVIEW A.4) Without it "daily change %" has no source: `previous_price` is the previous
*tick*, not the session baseline. The simulator pins its seed price as `session_open`; Massive uses
`day.previous_close`. `change_percent` (tick-over-tick) is retained and is NOT the daily number —
the two must never be confused in the UI.

**D-10 — Simulator `dt` is derived from `update_interval`.**
(REVIEW B.2.2) `SimulatorDataSource` currently accepts `update_interval` but never passes `dt` to
`GBMSimulator`, which falls back to a hardcoded 500ms constant. Setting `update_interval=0.1`
silently produces 5x the configured volatility. Correctness bug; fixed in this build.

**D-11 — `create_stream_router()` constructs its `APIRouter` inside the factory.**
(REVIEW B.2.5) Today it decorates a module-level router, so calling it twice registers duplicate
routes and the first closure's cache wins — which breaks any pytest fixture that builds two apps.

**D-12 — New env vars: `SIM_SEED`, `SIM_TICK_MS`, `MASSIVE_POLL_SECONDS`, threaded through the factory.**
(§13 #32, REVIEW B.2.1) `create_market_data_source()` currently exposes no configuration at all, so
PLAN §6's "configurable interval" claim is not implementable. `SIM_SEED` makes E2E price assertions
deterministic.

**D-52 — `SIM_VOL_MULTIPLIER` scales simulated volatility, default 1.0.**
A consequence of D-10: now that `dt` correctly tracks the tick rate, a faster tick produces
proportionally smaller moves, so `SIM_TICK_MS` cannot be used to liven up a demo. Realistic
volatility over a few seconds is sub-cent, which reads as a frozen screen. The multiplier is
applied to sigma at step time rather than baked into `seed_prices.py`, so the stored per-ticker
volatility still means what that file documents. Simulator only; it has no effect in Massive mode.

**D-13 — The SSE stream sends a keepalive comment frame when the cache version has not changed.**
(REVIEW A.3) Prevents idle proxies from dropping a connection that is legitimately quiet.

---

## 3. Portfolio and trade semantics

**D-14 — `trades` is authoritative. `positions` and `cash_balance` are a maintained projection.**
(§13 #21) This makes a future "recompute from trades" repair well-defined.

**D-15 — Position rows are deleted when quantity falls below 1e-9.** (§13 #17) Prevents float dust.

**D-16 — Rounding: cash 2dp, quantity 6dp, all comparisons via 1e-9 epsilon.** (§13 #18)

**D-17 — Realized P&L is out of scope.** (§13 #19) It is derivable from `trades` if wanted later.
Nothing stores or displays it in this build. Stated explicitly so no agent adds it speculatively.

**D-18 — Fill price is the current cached price at execution time.** No slippage, no fees, instant
fill, market orders only.

**D-19 — Trade validation, in this order:** (§13 #20)
1. Ticker canonicalizes and matches `^[A-Z]{1,5}$` -> else `INVALID_TICKER` (400)
2. Quantity is finite and > 0 -> else `INVALID_QUANTITY` (400)
3. A cached price exists -> else `PRICE_UNAVAILABLE` (409)
4. Buy: `cost <= cash_balance + epsilon` -> else `INSUFFICIENT_CASH` (400)
5. Sell: `quantity <= position.quantity + epsilon` -> else `INSUFFICIENT_SHARES` (400). No shorting.

**D-20 — Stale prices fill at the stale quote.** In Massive mode a quote up to `MASSIVE_POLL_SECONDS`
old is acceptable for a simulated portfolio. No staleness rejection.

**D-21 — `portfolio_snapshots`: one row at DB init, one every 30s, one after each trade. Retention
capped at 7 days, pruned by the same background task.** (§13 #22) Avoids an empty P&L chart for the
first 30 seconds and unbounded growth.

**D-22 — `GET /api/portfolio/history?limit=N` with `limit` defaulting to 500 and capped at 5000.**
(§13 #14) Newest-last ordering for direct charting.

---

## 4. API surface

**D-23 — One error envelope on every route: `{"error": {"code": "SCREAMING_SNAKE", "message": "human readable"}}`.**
(§13 #38) Codes are a closed set defined in `API_CONTRACT.md`. This resolves the 400-vs-409
contradiction between `archive/MARKET_DATA_DESIGN.md` and §13 #20 in favour of the codes above.

**D-24 — `GET /api/watchlist` returns tickers and metadata only, no prices.** (§13 #35) Prices come
from SSE. Serving them twice creates two sources of truth and a visible flicker.

**D-25 — Three endpoints are added beyond PLAN §8:**
- `GET /api/history/{ticker}` — server-side ring buffer, last 600 ticks per ticker, in memory.
  (§13 #12) Without it every chart is empty for the first seconds after a reload.
- `GET /api/chat` — conversation history, so a reload does not show an empty panel while the DB
  grows. (§13 #13) `chat_messages` persistence is therefore KEPT, resolving §13 #39.
- `POST /api/reset` — restores the seeded state ($10k cash, default watchlist, no positions).
  (§13 #33) Also the cleanest per-test fixture for E2E.

**D-26 — `GET /api/health` returns market source, seconds since last tick, tracked ticker count, and
DB reachability.** (§13 #30) E2E waits on a real readiness signal instead of sleeping.

**D-27 — Timestamps: ISO-8601 UTC strings in all DB-backed JSON. The SSE payload keeps Unix float
seconds.** (§13 #16) The SSE shape is already shipped and its consumer is a charting library that
wants epoch numbers. The frontend has exactly one conversion point, at the SSE parse boundary.

---

## 5. LLM integration

**D-28 — Model: `openrouter/openai/gpt-oss-120b` via LiteLLM -> OpenRouter with the Cerebras provider,**
per `.claude/skills/cerebras/SKILL.md`. (REVIEW B.1.6 — the skill's `name:` is `cerebras-inference`
but it lives at `.claude/skills/cerebras/`.)

**D-29 — Structured output support must be verified empirically before the chat feature is built.**
(§13 #25) If strict JSON-schema `response_format` is not honored on this route, fall back to
`json_object` mode plus one parse-and-repair retry. This is a build-time verification task, not an
assumption.

**D-30 — Conversation history window: last 20 messages, truncated to 8000 characters total.** (§13 #23)

**D-31 — LLM failures return HTTP 200 with `{"message": "<friendly text>", "error": true, ...}`.**
(§13 #24) A 502 forces the frontend to invent an error bubble. Request timeout 30s, one retry on
timeout or unparseable JSON, then give up gracefully.

**D-32 — Actions execute independently; each records `status` and `error`.** (§13 #27) If the LLM
returns three trades and the second fails validation, the other two still execute and all three
outcomes are recorded in `chat_messages.actions` and returned.

**D-33 — `LLM_MOCK=true` contract is deterministic and keyed off the input text:** (§13 #26)
| Input matches | Mock response |
|---|---|
| `/\b(buy\|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares\s+of\s+)?([A-Za-z]{1,5})\b/i` | message confirming the trade + one matching `trades` entry |
| `/\b(add\|remove)\s+([A-Za-z]{1,5})\b.*watchlist/i` | message + one matching `watchlist_changes` entry |
| `/\b(portfolio\|position\|holding)/i` | canned portfolio analysis referencing real context values, no actions |
| anything else | canned greeting/analysis, no actions |
Backend and E2E tests both build against this table. Without it the two halves drift.

**D-34 — Auto-execution stays unconfirmed.** Fake money, zero stakes, and demonstrating agentic
execution is the point of the project.

---

## 6. Runtime, packaging, operations

**D-35 — SQLite: WAL mode, `check_same_thread=False`, `aiosqlite` for async access.** (§13 #28)

**D-36 — DB initialization happens in the FastAPI lifespan, before the market source starts.**
(REVIEW B.3.1) PLAN §4's "lazy init on first request" is incompatible with
`MarketDataSource.start(tickers)` needing the ticker list at startup. Startup order is:
open DB -> init schema + seed if empty -> read the union ticker set -> start market source ->
start snapshot task -> serve.

**D-37 — The backend reads environment variables only. `python-dotenv` loads `.env` for local
(non-Docker) development.** (§13 #3) Docker passes `--env-file`, so there is no project-root `.env`
inside the container to read.

**D-38 — Docker uses a bind mount: `-v "$(pwd)/db:/app/db"`.** (§13 #1) A named volume makes
`db/.gitkeep` inert and hides `trader.db` from the user.

**D-39 — Port binding is localhost-only: `-p 127.0.0.1:8000:8000`.** (§13 #29) The app has no auth
and auto-executes trades; it must not be exposed to the LAN by default.

**D-40 — The start script opens the browser, with a flag to suppress.** (§13 #2)

**D-41 — `docker compose up/down` is the single code path. The platform scripts become one-line
wrappers.** (§13 #34) Five artifacts with two code paths otherwise drift.

**D-42 — Production image installs `uv sync --frozen --no-dev`.** (REVIEW B.1.5) `rich` moves to the
dev extra; it exists only for `market_data_demo.py`.

**D-43 — Repo hygiene, fixed in this build:** (REVIEW B.1.1–B.1.4) Node/Next entries in
`.gitignore`; `db/*.db*` ignored and `db/.gitkeep` created; `.env.example` at the project root; a
`.dockerignore`; and `ci.yml` running ruff, pytest, frontend lint/tests, and a Docker build.

**D-44 — Massive mode outside market hours goes static, and that is expected.** (§13 #31) Documented
in the README. No automatic fallback to the simulator: silently swapping real data for fake data is
worse than a frozen display.

---

## 7. Frontend

**D-45 — Header total value is recomputed client-side on every SSE tick** from positions x live
prices. (§13 #41) The `GET /api/portfolio` value is the reconciliation point, not the live number.

**D-46 — UI state (selected ticker, chat collapse) is ephemeral.** (§13 #42) No localStorage.

**D-47 — No double-submit protection beyond disabling the button while a request is in flight.**
(§13 #43) Idempotency keys are out of scope for a fake-money demo.

**D-48 — Color tokens are defined in `API_CONTRACT.md`'s companion design token block, contrast
checked against `#0d1117`, and P&L is never encoded by color alone** — sign and an arrow glyph
accompany every colored value. (§13 #15, REVIEW B.3.11, C.6)

---

## 8. Process

**D-49 — Handoff convention:** one `planning/<COMPONENT>_SUMMARY.md` per completed component;
working documents move to `planning/archive/`. (§13 #44) `MARKET_DATA_SUMMARY.md` is the precedent.

**D-50 — Definition of done, per component:** code + unit tests passing + ruff clean + the relevant
E2E scenario green + a `*_SUMMARY.md` written + CI green. (REVIEW C.3)

**D-51 — The market-data unit tests in PLAN §12 are already done** (73 tests, 84% coverage) and are
not to be rewritten. (§13 #40) New tests cover the three bug fixes in D-06, D-10, D-11.
