# PLAN.md — Second Review Pass

Date: 2026-08-17
Scope: `planning/PLAN.md` (all sections, including the existing §13 review pass), cross-checked
against `planning/MARKET_DATA_SUMMARY.md` and the shipped code in `backend/app/market/`, plus the
actual repository state.

This review deliberately does **not** re-litigate the 44 items in §13. It covers three things:

- **Part A** — where §13 is factually wrong or overstated when checked against the code that
  actually shipped, and where it stopped one step short.
- **Part B** — substantive gaps §13 missed entirely, ordered by blast radius.
- **Part C** — PLAN.md's coherence *as a build contract* for parallel agents, which is the
  document's actual job and its weakest dimension.
- **Part D** — prioritized action list.

Verdict up front: **§1–§12 are a good product brief and a weak engineering contract.** The prose is
clear, the scope is well-chosen, and the rationale table in §3 is genuinely useful. But the document
specifies *what the app is* far more precisely than *what each agent must produce and how the pieces
snap together*. §13 correctly identified ~40 under-specified details; it did not identify that the
document has no build order, no ownership map, no definition of done, and no composition root — and
those are the failures that actually stall a parallel agent build. §13 also introduced a new problem
of its own (Part C.1).

---

## Part A — Corrections and additions to §13

### A.1 §13 #8 is wrong about the shipped simulator

§13 #8 asserts "the simulator only has seed prices for known symbols" and asks for "a synthetic seed
price for unknown symbols in simulator mode." That already exists. `backend/app/market/simulator.py`:

```python
self._prices[ticker] = SEED_PRICES.get(ticker, random.uniform(50.0, 300.0))
self._params[ticker] = TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))
```

Unknown tickers get a random price in `[50, 300]` and `DEFAULT_PARAMS` (`sigma=0.25, mu=0.05`). The
real problem is the opposite of the one §13 describes, and it is worse:

- **The simulator silently accepts any string.** `POST /api/watchlist {"ticker": "ZZZZ"}` will
  produce a plausible-looking live price for a symbol that does not exist. An LLM hallucinating
  `NVDIA` gets a tradeable instrument. There is no validation layer anywhere, and the simulator's
  permissiveness means a validation bug will never surface as an error — only as fake data.
- **The two sources diverge on unknown symbols.** Simulator: invents a price. Massive: the ticker is
  simply absent from the snapshot response, `_poll_once` updates nothing, and the cache entry never
  appears — a silent no-op with no error and no log line. So the same user action produces two
  completely different behaviours depending on an env var, which violates §6's core promise that
  "all downstream code is agnostic to the source."

**Recommendation:** replace §13 #8 with: a shared ticker validation step (regex `^[A-Z]{1,5}$` plus
an allowlist or a Massive `GET /v3/reference/tickers` lookup when in Massive mode), and an explicit
contract that `add_ticker` on an unknown symbol raises a defined error in *both* sources rather than
inventing a price in one and no-op'ing in the other.

### A.2 §13 #9 (watchlist cap) is based on a wrong premise

§13 #9 says a large watchlist "either blows the 5-calls/min free tier or forces a grouped endpoint."
The shipped client already uses the grouped endpoint — `massive_client.py` calls
`get_snapshot_all(market_type=SnapshotMarketType.STOCKS, tickers=self._tickers)`, i.e. **one HTTP
call per poll regardless of ticker count**. Adding 40 symbols costs zero extra API calls.

A cap is still worth having, but for the reasons §13 didn't give:

- Every SSE frame serializes **all** tickers (`stream.py` sends the full map), so payload size is
  O(n) at 2 Hz. 10 tickers is ~1.5 KB/frame; 100 tickers is ~15 KB/frame = 30 KB/s per client.
- `_rebuild_cholesky()` is O(n²) to build and O(n³) to decompose, and it runs synchronously inside
  the event loop on every `add_ticker`/`remove_ticker`.
- Massive's snapshot endpoint has its own URL-length / ticker-count limits per request.

So the cap belongs in the plan, but justify it on payload and Cholesky cost, not rate limits, and
state it as a hard limit enforced in the same helper as canonicalization (§13 #10).

### A.3 §13 #4 (SSE shape) — correct, but incomplete in three ways

Agreed on the core point: §6 describes per-ticker events and the code sends one map-shaped event.
§13's suggested replacement text is still missing details the frontend agent will need on day one:

1. **There is no `event:` name.** The frontend must use `EventSource.onmessage`, not
   `addEventListener('price', ...)`. Worth one sentence — this is a classic silent-failure mode.
2. **There is no heartbeat.** `_generate_events` only yields when `price_cache.version` changes.
   If the source stops producing (zero tracked tickers, or a poll failure loop in Massive mode
   overnight per §13 #31), the connection sends **zero bytes indefinitely**. Idle-timeout-enforcing
   intermediaries (nginx, AWS App Runner per §11's deployment goal, corporate proxies) will drop it
   at 30–60s. EventSource will reconnect, but the UI's connection dot will flap and §12's "SSE
   resilience" test becomes unreliable. Specify a comment keepalive (`: ping\n\n`) every ~15s.
3. **The initial frame is not guaranteed.** `last_version` starts at `-1` so the first loop
   iteration does emit — but only if the cache is non-empty (`if prices:`). A client connecting
   before `source.start()` completes gets nothing until the next tick. Combined with §13 #12's empty
   chart, this is the actual first-paint story and it should be stated.

### A.4 §13 #11 (daily change %) — right diagnosis, and it's worse than stated

Confirmed: `PriceUpdate` has no session baseline. But note that `change_percent` **does** exist on
the model and is serialized into every SSE frame:

```python
"change": self.change,                # price - previous_price  (per tick)
"change_percent": self.change_percent # per tick, not per day
```

This is a naming trap. A frontend agent reading the SSE payload will find a field literally called
`change_percent`, wire it to §10's "daily change %" column, and ship a number that is ~0.001% and
flickers around zero. The bug will look like a styling problem, not a data problem.

**Add to §13 #11:** rename the per-tick fields (`tick_change`, `tick_change_percent`) *or* add
`session_open` + `day_change_percent` alongside them, and state explicitly in the plan which field
feeds which UI element. This is a one-line spec change that prevents a subtle, hard-to-spot defect.

### A.5 §13 #40 (mark market-data tests done) — agreed, with a caveat

Agreed that §12's market-data bullets are satisfied. Two caveats before anyone crosses them off:

- `test_massive.py` covers `massive_client.py` at **56%** (per `MARKET_DATA_SUMMARY.md`), with the
  API methods mocked. §12 claims "Massive API response parsing works" is tested — it is tested
  against a mock whose shape was written by the same agent. That is not the same as verified.
  Flag it as "simulator: done; Massive: mock-verified only."
- There is **no CI running these tests.** `.github/workflows/` contains only `claude.yml` and
  `claude-code-review.yml`. The 73 tests pass on whoever's laptop last ran them. See B.1.4.

### A.6 §13 #34 (compose over scripts) contradicts §3 and doesn't say so

§13 #34 recommends `docker compose up/down` as the primary path. §3's rationale table says
"Single Docker container | Students run one command; **no docker-compose for production**, no
service orchestration." If #34 is adopted, that table row must be rewritten — otherwise the plan
argues against itself in two places. Also note §12 already mandates a `docker-compose.test.yml`, so
the "no compose" position is already half-abandoned. Recommend: adopt compose everywhere and change
the §3 row to "Single container, orchestrated by Compose for convenience."

---

## Part B — Gaps §13 missed

### B.1 Repository-level gaps (concrete, cheap to fix, currently broken)

**B.1.1 `.gitignore` is Python-only. A Next.js frontend will be committed wholesale.**
`.gitignore` is the stock GitHub Python template. It has no `node_modules/`, no `.next/`, no `out/`,
no `frontend/.env.local`. The moment the Frontend Engineer agent runs `npm install`, the next
`git add -A` stages tens of thousands of files. §4 explicitly names `.gitignore` as a project
artifact but never says what belongs in it.
**Fix:** add the Node/Next entries to `.gitignore` *before* the frontend agent starts, and note it
in §4.

**B.1.2 `db/trader.db` is not actually gitignored.**
§4 states "`trader.db` is gitignored". The only DB-ish entries in `.gitignore` are `db.sqlite3` and
`db.sqlite3-journal` (Django template leftovers). `db/trader.db`, `*.db`, `*.db-wal`, `*.db-shm`
are all untracked-but-not-ignored. With WAL mode on (§13 #28), that's three files per run.
**Fix:** add `db/*.db*` and create `db/.gitkeep`. Neither `db/` nor `.gitkeep` exists in the repo
today, despite §4 listing both.

**B.1.3 `.env.example` does not exist, and `README.md` tells users to copy it.**
`README.md` line 30: `cp .env.example .env`. That file is not in the repo. §4 says it is committed.
This is the very first command in the quick start and it fails.
**Fix:** create `.env.example` from §5's block. Also decide who owns README accuracy — currently
nobody.

**B.1.4 No CI. No `.dockerignore`.**
There is no workflow that runs `pytest`, `ruff`, or a Docker build. §12 defines a testing strategy
with no execution trigger, which in a multi-agent build means later agents can break the market data
module and nothing will notice until a human runs the suite. Separately, `.dockerignore` is never
mentioned anywhere in §4 or §11 — without it the multi-stage build will copy `node_modules/`,
`.venv/`, `.git/`, and `db/trader.db` into the build context.
**Fix:** add a `ci.yml` (pytest + ruff + `npm test` + `docker build`) to §4's tree and a
`.dockerignore` to both §4 and §11. State that CI green is part of the definition of done.

**B.1.5 The backend cannot yet run the features §9 specifies.**
`backend/pyproject.toml` dependencies are `fastapi, uvicorn, numpy, massive, rich`. Missing:
`litellm` and `pydantic` (required by the cerebras skill at `.claude/skills/cerebras/SKILL.md`),
`python-dotenv` (§13 #3's recommendation), and any SQLite async driver (`aiosqlite`, per §13 #28).
`rich` is a *production* dependency solely for `market_data_demo.py` — it ships in the Docker image
for a dev-only script and should move to the `dev` extra.
**Fix:** §11's Dockerfile sketch should say `uv sync --frozen --no-dev` (it currently just says
`uv sync`, which will install pytest/ruff/rich into the production image).

**B.1.6 The skill is named `cerebras-inference` but lives at `.claude/skills/cerebras/`.**
§9 says "use cerebras-inference skill". The frontmatter `name:` is `cerebras-inference`, the
directory is `cerebras`. This works, but §9 should reference the path so an agent that greps for
`cerebras-inference` in the filesystem doesn't conclude the skill is missing.

### B.2 Drift between PLAN.md and the shipped market data code (beyond §13 #4)

**B.2.1 §6 promises a "configurable interval"; the factory exposes no configuration at all.**
`create_market_data_source(price_cache)` takes only the cache and reads only `MASSIVE_API_KEY`.
`MassiveDataSource.poll_interval` (default 15.0) and `SimulatorDataSource.update_interval` /
`event_probability` are constructor arguments the factory never passes. So §6's "Paid tiers: poll
every 2-15 seconds depending on tier" is **not implementable without a code change**. §13 #32 asks
for `SIM_SEED`/`SIM_TICK_MS` but misses that the existing knobs are already unreachable.
**Fix:** either add `MASSIVE_POLL_SECONDS` / `SIM_TICK_MS` / `SIM_SEED` to §5 and thread them
through the factory, or delete the "configurable" claim from §6.

**B.2.2 The simulator's `dt` is decoupled from its tick rate — a latent correctness bug.**
`SimulatorDataSource.__init__` accepts `update_interval` but constructs
`GBMSimulator(tickers=..., event_probability=...)` **without passing `dt`**. `GBMSimulator` falls
back to `DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR`, which hardcodes a 500 ms tick. Set
`update_interval=0.1` (a plausible thing for an E2E agent to do to speed up tests) and realized
volatility silently becomes 5× the configured `sigma`. §12 claims "GBM math is correct" is unit
tested; the tests verify the formula, not this wiring.
**Fix:** `dt` must be derived from `update_interval` in `SimulatorDataSource.start()`. Worth calling
out in the plan because it is exactly the kind of thing a later agent will "helpfully" reconfigure.

**B.2.3 Ticker canonicalization is inconsistent *between the two shipped sources*.**
`MassiveDataSource.add_ticker` does `ticker.upper().strip()`. `SimulatorDataSource.add_ticker` does
not — it passes the raw string straight to `GBMSimulator.add_ticker`, which keys `_prices` and
`_tickers` by it. So `add_ticker("aapl")` in simulator mode creates a *second*, independent
instrument alongside `AAPL`, with its own random seed price, both streaming to the UI. §13 #10 asks
for canonicalization at the API boundary; it missed that the inconsistency already exists one layer
down and will survive a correct API-layer fix if anything ever calls the source directly.
**Fix:** normalize inside both sources (defence in depth), and say so in §6.

**B.2.4 `remove_ticker` deletes the price from the cache — which breaks §13 #5's own recommendation.**
Both sources call `self._cache.remove(ticker)` in `remove_ticker`, and `MarketDataSource`'s docstring
mandates it: *"Also removes the ticker from the PriceCache."* §13 #5/#6 recommend the union rule
(keep held tickers in the price source when un-watchlisted) — that recommendation is compatible with
the code, but only because the union rule means you never call `remove_ticker` for a held ticker.
The plan should state that invariant explicitly, because the failure mode is nasty: removing a held
ticker nukes its cached price, `get_price()` returns `None`, and portfolio valuation either crashes
or silently values the position at 0, tanking the P&L chart and the heatmap.
**Fix:** add to §7/§8: *"`source.remove_ticker` may only be called for tickers with no open
position. Portfolio valuation must treat a missing cached price as an error, never as 0."*

**B.2.5 `create_stream_router` mutates a module-level global.**
`stream.py` defines `router = APIRouter(...)` at module scope, and `create_stream_router()` registers
`@router.get("/prices")` on that shared instance and returns it. Calling it twice (two app instances
in one process — exactly what a pytest suite with an app fixture does) registers duplicate routes on
the same router, and the *first* closure's `price_cache` wins for the first matching route. The
docstring claims the factory pattern "lets us inject the PriceCache without globals" — it does the
opposite.
**Fix:** move `APIRouter(...)` inside the factory. Small, but it will bite the API-routes agent the
moment they write a `TestClient` fixture.

**B.2.6 Seed prices are stale and undated in the plan.**
`seed_prices.py` comments say "as of project creation" (AAPL 190, NVDA 800, MSFT 420). §6 says
"Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)" — hardcoding sample values
into the spec. When these drift further from reality, two places need updating and the plan will be
the one that gets missed.
**Fix:** §6 should say "seed prices live in `backend/app/market/seed_prices.py`" and drop the
inline examples.

**B.2.7 `MARKET_DATA_SUMMARY.md` itself has two small inaccuracies.**
The modules table describes `PriceUpdate` as "(ticker, price, previous_price, timestamp, change,
direction)" — omitting `change_percent`, which *is* in `to_dict()` and is precisely the field most
likely to be misused (A.4). And the "Usage for Downstream Code" snippet omits `create_stream_router`
entirely, so an agent reading only the summary won't know the SSE endpoint needs wiring.

### B.3 Specification gaps §13 didn't reach

**B.3.1 DB init timing contradicts the market data source's own API.**
§7 says the backend initializes the DB "on startup (or first request)"; §4 says "lazily initializes
the database **on first request**." But `MarketDataSource.start(tickers)` requires the ticker list
**at boot**, and §6 says the background task starts with the app. If DB init is deferred to the
first request, there is no watchlist at `start()` time and the price source begins with an empty
ticker set — meaning the first client to connect sees an empty SSE stream until something reconciles.
This is a hard ordering contradiction between §4/§7 and an already-shipped interface, and §13 missed
it entirely.
**Fix:** state a single startup sequence in §7, e.g.:
`lifespan → init/seed DB → read union(watchlist, positions) → source.start(tickers) → serve`.
Then delete "or first request" everywhere.

**B.3.2 There is no composition root, and no agent owns it.**
The repo has `backend/app/market/` and nothing else — no `app/main.py`, no `app/__init__.py` content
beyond a stub, no FastAPI instance, no lifespan handler. §4's "Key Boundaries" assigns `frontend/`
to the Frontend Engineer and `backend/` to "the Backend/Market Data agents" (plural, unnamed). Nobody
owns: creating the app, mounting `create_stream_router`, mounting `StaticFiles` last so it doesn't
shadow `/api/*`, wiring lifespan startup/shutdown (`await source.stop()` is never called anywhere
today), and configuring logging.
**Fix:** name the file (`backend/app/main.py`), name its owner, and enumerate its responsibilities
in §4. This is the single highest-risk unassigned artifact in the project — every other agent
depends on it and none of them can be told to build it.

**B.3.3 The core portfolio formulas are never written down.**
§8 says `GET /api/portfolio` returns "total value, unrealized P&L" and §10 says the positions table
shows "unrealized P&L, % change" — but the plan never defines a single one of these. Three agents
(backend, frontend header, LLM context builder) will each derive their own, and they will disagree
at the margins. Missing definitions:
- `market_value = quantity * current_price`
- `total_value = cash_balance + Σ market_value` (does it include pending anything? no — say so)
- `unrealized_pnl = quantity * (current_price - avg_cost)`
- `% change` denominator — `avg_cost` (position return) or previous close (daily return)? §10's
  positions table and §10's watchlist "daily change %" are **different percentages** and currently
  read as if they might be the same.
- `avg_cost` on a sell: unchanged (only `quantity` decreases). Trivial, universally known, and
  exactly the kind of thing that gets implemented as a weighted average by mistake.
- Buy: `avg_cost = (old_qty*old_avg + fill_qty*fill_price) / (old_qty + fill_qty)`.
§13 #17–#21 circle this area (rounding, lifecycle, realized P&L) without ever stating the base
formulas. Six lines of arithmetic in §7 removes an entire class of cross-agent disagreement.

**B.3.4 Fill price is undefined, and it is user-visible.**
§2 says "instant fill at current price." Which current price? The cache value at request time — but
the user clicked based on a price rendered from an SSE frame up to 500 ms old (or, in Massive mode,
up to 15 s old per §13 #20). The plan should state: *fills execute at `PriceCache.get_price(ticker)`
at the moment of execution; the response includes the fill price; the UI displays the fill price
rather than assuming it matches the quote.* Otherwise the trade confirmation and the watchlist will
show different numbers for the same instant and it will look like a bug.

**B.3.5 Watchlist ordering is unspecified.**
`watchlist` has `added_at`, but §8's `GET /api/watchlist` never states an order, and the SSE payload
is a **JSON object keyed by ticker** — insertion-ordered by whatever `dict(self._prices)` happens to
contain. A frontend that renders `Object.entries(payload)` will get rows that reorder when a ticker
is added or when the cache dict is rebuilt. §10 requires a stable, dense, terminal-style grid; row
churn at 2 Hz is visually disqualifying.
**Fix:** state that the watchlist REST response is ordered by `added_at ASC` and that the frontend
renders from the watchlist order, using the SSE map purely as a price lookup.

**B.3.6 Held-but-unwatched tickers have no UI story.**
Under §13 #5/#6's union rule, you can hold NFLX with NFLX absent from the watchlist. §10 then puts
NFLX in the heatmap and the positions table but not the watchlist panel — and clicking it in the
positions table has no defined behaviour ("Click a ticker" is specified only for the watchlist in
§2). Decide: does the positions table also select the main chart? Is there a visual marker for
"held, not watched"?

**B.3.7 Next.js static export ↔ FastAPI serving has unaddressed sharp edges.**
§3/§11 say "FastAPI serves the static frontend files and all API routes on port 8000" and stop
there. Real decisions nobody owns: App Router or Pages Router; `trailingSlash` config (affects
whether `/foo` or `/foo/index.html` resolves); the SPA fallback for unknown paths (a static export
has no server, so FastAPI must decide between 404 and serving `index.html`); cache headers
(`index.html` must be `no-store` or students will get a stale bundle after a rebuild, while
`/_next/static/*` is content-hashed and should be immutable); and route-mount ordering so the
catch-all doesn't shadow `/api`. Also §11 says `npm install` where `npm ci` is correct for a
reproducible lockfile-driven Docker build.

**B.3.8 Concurrency and idempotency of the *chat* path is unaddressed.**
§13 #43 waves at double-clicking the buy button. The larger version is unaddressed: `POST /api/chat`
auto-executes trades and takes seconds. Two overlapping chat requests, or a chat request overlapping
a manual trade, will interleave reads and writes of `cash_balance` with no stated transaction
boundary. State it: *trade execution (read balance → validate → write position + cash + trade row)
happens inside a single SQLite transaction (`BEGIN IMMEDIATE`), and the chat endpoint serializes on
a per-user lock.* Cheap to implement, impossible to retrofit cleanly.

**B.3.9 Prompt injection into an auto-executing trade loop is not acknowledged.**
§9 auto-executes LLM-specified trades with no confirmation, and §9 step 1 feeds "portfolio context"
into the prompt — context that contains **user-controlled ticker strings** from the watchlist. It is
fake money, so the risk is genuinely near-zero, but the plan is a teaching artifact for an AI coding
course and currently presents unconfirmed tool-execution as an unqualified good ("the stakes are
zero"). One paragraph noting that this pattern is safe *here specifically because* the blast radius
is a simulated $10k, and that a real system would require confirmation for state-changing actions,
would substantially improve the plan's value as course material.

**B.3.10 §12 lists no failure-path E2E scenarios.**
All seven "Key Scenarios" are happy paths. Missing and cheap: buy with insufficient cash shows an
error; sell more shares than held shows an error; add a duplicate ticker; add an invalid ticker;
LLM returns malformed JSON (mock mode can force this). These are precisely the paths where §13's
undecided error-envelope question (#38) will otherwise be discovered late.

**B.3.11 No performance or resource budget.**
"Data-dense" + 2 Hz SSE + treemap + two charts is a real render-load question, and the plan gives
the frontend agent no target. State something falsifiable: 60 fps with 25 watchlist rows, main chart
holding ≤ 600 points, sparkline ≤ 60 points, SSE-driven React state updates batched per frame rather
than per event. Without a number, "visually stunning" and "performant" will be traded off silently.

---

## Part C — Coherence as a build contract

### C.1 §13 is now the largest section of the contract, and every item is unresolved

This is the most important structural point in this review. `CLAUDE.md` does `@planning/PLAN.md`,
so **the entire plan — including all 44 open questions — is injected into every agent's context in
every session.** The result:

- ~35% of the contract document consists of questions with recommendations but no decisions. An
  agent reading §6 gets a specification; the same agent reading §13 #4 is told that specification is
  wrong. There is no marker saying which wins.
- Several §13 items contradict §1–§12 outright (#34 vs §3's rationale table, #35 vs §8's
  `GET /api/watchlist` description, #39 vs §7's `chat_messages` table). An agent will implement one
  or the other essentially at random.
- The `[decide]` items are labelled as needing an answer "before the relevant component is built" —
  but nothing tracks whether that happened, and nothing records the answer.

**Fix (highest-leverage change in this review):**
1. Resolve the §13 items — most have a recommendation attached; accept or reject each in one line.
2. Fold the accepted answers **into §1–§12 as normative text**, so the spec is internally consistent
   and self-contained.
3. Move the decision log to `planning/DECISIONS.md` (ID, question, decision, date, rationale) and
   **delete §13 from PLAN.md.**
4. PLAN.md then reads as a contract with no open questions, which is what an agent needs. The
   history is preserved but out of the always-loaded context.

### C.2 There is no build order, no dependency graph, no phases

The plan describes eight subsystems as if they can all start at once. They cannot:

- `app/main.py` + DB init + schema must exist before *anything* else in the backend.
- The API contract must be frozen before the frontend can build against it.
- `LLM_MOCK` semantics (§13 #26) must be frozen before E2E can be written.
- The Dockerfile can't be finished until the frontend build output path is known.

§1 says agents "interact through files in `planning/`" and that is the entire process description.
**Fix:** add a §14 "Build Sequence" with numbered phases, the artifact each phase produces, and the
explicit unblock condition for the next. Something like: (0) repo hygiene — `.gitignore`,
`.dockerignore`, `.env.example`, CI; (1) `API_CONTRACT.md` frozen (§13 #37 — agreed, this is the
right call); (2) backend core — main.py, DB, portfolio, watchlist; (3) frontend + LLM in parallel
against the frozen contract; (4) Docker; (5) E2E.

### C.3 There is no definition of done, at any level

Nothing in the plan says when a component is finished. `MARKET_DATA_SUMMARY.md` implies the de facto
bar (implemented + tested + reviewed + summary written + coverage reported), but that convention is
undocumented — §13 #44 spots the summary-file convention gap and stops at file naming. State the
actual gate: tests pass, `ruff` clean, coverage ≥ N%, code review pass completed, `*_SUMMARY.md`
written, CI green, and PLAN.md updated where the implementation diverged. Without this, "the market
data component is complete" and "the frontend is complete" mean different things.

### C.4 The agent roster is genuinely absent

§4 references "the Frontend Engineer agent" and "the Backend/Market Data agents"; §1 says the
project is "built entirely by Coding Agents." There is no list. `.claude/agents/` contains exactly
one agent (`reviewer.md`). So the plan's ownership assignments point at roles that do not exist as
configured agents. Either define the roster in the plan (name, scope, owned directories, handoff
artifact) or stop referring to specific agent roles in §4 — the current halfway state implies an
org chart that isn't there.

### C.5 No requirement is traceable, and non-functional requirements are unfalsifiable

Nothing in §1–§12 is numbered or ID'd, so §13 has to say "§10 requires..." in prose and a reviewer
has to re-read whole sections to check coverage. More importantly, the headline requirements are
untestable as written: "visually stunning" (§1), "every pixel earns its place" (§2), "production-
quality" (§1), "functional on tablet" (§2 — at what breakpoint?). §12 has no acceptance criteria for
any of them. At minimum, pin the tablet breakpoint (e.g. ≥ 768 px) and replace "visually stunning"
with a short checklist the frontend agent can self-assess against (the §2 visual-design bullets are
already 80% of that checklist — just promote them to acceptance criteria).

### C.6 Missing cross-cutting concerns

Never mentioned anywhere in §1–§12: logging (format, levels, where — the market module already uses
stdlib `logging` with no configured handler, so those `logger.info` calls currently go nowhere);
error handling philosophy beyond §13 #38's envelope; graceful shutdown (`source.stop()` has no
caller); container healthcheck (`HEALTHCHECK` instruction — §11 mentions `/api/health` is "for
Docker/deployment" but never wires it); non-root container user; timezone handling (§13 #16 covers
format but not that all ISO timestamps must be UTC with an explicit `Z`); and accessibility (a
red/green-only P&L encoding is the single most common colour-blindness failure, and §13 #15 asks for
the colour tokens without mentioning that they need a non-colour redundant cue).

---

## Part D — Prioritized actions

**Do before any further code is written:**

1. Resolve §13, fold decisions into §1–§12, move the log to `DECISIONS.md`, delete §13 (C.1).
2. Write `planning/API_CONTRACT.md` and freeze it (§13 #37 — agreed, highest-leverage item there).
   Include the corrected SSE shape with the A.3 additions and the A.4 field-naming fix.
3. Add §14 "Build Sequence" with phases and unblock conditions (C.2), and a definition of done (C.3).
4. Assign `backend/app/main.py` to a named owner and enumerate its responsibilities (B.3.2).
5. Fix repo hygiene now: `.gitignore` (Node + `db/*.db*`), `.dockerignore`, `.env.example`, a
   `ci.yml` that runs pytest + ruff (B.1.1–B.1.4).

**Do before the backend/portfolio agent starts:**

6. Write the portfolio formulas into §7 (B.3.3) and define fill-price semantics (B.3.4).
7. Fix the DB-init-timing contradiction with an explicit startup sequence (B.3.1).
8. State the transaction boundary and chat serialization (B.3.8).
9. State the `remove_ticker`/held-position invariant and ban valuing a missing price as 0 (B.2.4).

**Do before the frontend agent starts:**

10. Rename or supplement `change_percent`; state which field feeds "daily change %" (A.4).
11. Specify watchlist ordering and the held-but-unwatched UI story (B.3.5, B.3.6).
12. Settle the Next.js export details: router choice, `trailingSlash`, SPA fallback, cache headers,
    mount ordering, `npm ci` (B.3.7).
13. Add the performance budget and the accessibility cue for P&L colour (B.3.11, C.6).

**Code fixes to schedule against the already-shipped module:**

14. Derive `dt` from `update_interval` in `SimulatorDataSource.start()` (B.2.2) — correctness bug.
15. Move `APIRouter(...)` inside `create_stream_router` (B.2.5).
16. Normalize tickers inside `SimulatorDataSource.add_ticker`/`GBMSimulator` (B.2.3).
17. Add an SSE keepalive comment frame (A.3).
18. Thread poll/tick/seed config through `create_market_data_source`, or drop §6's "configurable"
    claim (B.2.1).
19. Move `rich` to the `dev` extra; add `litellm`, `pydantic`, `python-dotenv`, `aiosqlite` (B.1.5).

**Documentation touch-ups:**

20. Drop inline seed prices from §6 and point at `seed_prices.py` (B.2.6).
21. Correct `MARKET_DATA_SUMMARY.md` (`change_percent`, `create_stream_router`) (B.2.7).
22. Reference the skill by path in §9 (B.1.6).
23. Add the "why unconfirmed auto-execution is acceptable *here*" paragraph to §9 (B.3.9).
24. Add failure-path E2E scenarios to §12 (B.3.10).

---

## What the plan gets right

Worth stating, because a review of this length can read as a verdict on quality rather than on
completeness:

- The scope decisions are excellent. Market-orders-only (§3), no auth (§3), SSE over WebSockets
  (§3), and static export over a second server (§3) each remove a whole category of work, and the
  rationale table explains *why* rather than just asserting.
- §7's `user_id` column on every table is exactly the right amount of future-proofing: near-zero
  cost now, avoids a migration later.
- The `MarketDataSource` ABC + `PriceCache` split (§6) has already proven itself — the shipped code
  swaps simulator for Massive with no downstream awareness, which is what §6 promised.
- `LLM_MOCK` (§5, §9) as a first-class, documented mode is a genuinely good call for a course
  project and for E2E determinism.
- §2's visual design bullets are concrete enough to build from, which is rare in a UX section.
- `MARKET_DATA_SUMMARY.md` is a good handoff artifact and the right template for future components —
  it just needs to be codified as a convention (C.3, and §13 #44).
