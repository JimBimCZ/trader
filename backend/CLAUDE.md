# Backend — Developer Guide

FastAPI application serving the REST API, the SSE price stream, and the exported frontend.

## Setup

```bash
cd backend
uv sync --extra dev
```

## Commands

```bash
uv run --extra dev pytest                      # 492 tests, needs Postgres (see Testing below)
uv run --extra dev pytest --cov=app            # with coverage
uv run --extra dev pytest tests/portfolio -v   # one area
uv run --extra dev ruff check app/ tests/      # lint
uv run ruff format app/ tests/                 # format

uv run uvicorn app.main:app --reload           # dev server on :8000
STATIC_DIR=../frontend/out uv run uvicorn app.main:app   # with the built frontend
```

## Layout

| Path | Responsibility |
|---|---|
| `app/main.py` | `create_app()` and the lifespan that wires everything together |
| `app/config.py` | `Settings`, read once from the environment |
| `app/clock.py` | `now_ts()` / `utcnow_iso()` — the single time seam; patch these in tests |
| `app/errors.py` | `AppError` subclasses and the JSON error envelope |
| `app/deps.py` | FastAPI dependencies: resolves the caller from the session cookie, then builds each service per request, scoped to that user |
| `app/identity/` | The signed session cookie (`cookie.py`), the user record (`models.py`), and the user store — mint/load/touch/expire (`store.py`) |
| `app/reconcile.py` | Owns the tracked-ticker set, globally across every user |
| `app/db/` | Postgres connection, schema, per-user seed, migrations |
| `app/market/` | Simulator, Massive client, price cache, SSE |
| `app/portfolio/` | Trades, valuation, snapshots |
| `app/watchlist/` | Watchlist CRUD |
| `app/history/` | In-memory price ring buffer |
| `app/llm/` | Chat, structured outputs, mock client |
| `app/system/` | Health, reset, guest cleanup |

Each domain is repository → service → router. Logic goes in the service, SQL in the repository,
HTTP translation only in the router.

## Invariants worth knowing before you change anything

1. **Only `reconcile.py` may call `source.remove_ticker()`.** It also evicts the cached price, so
   calling it for a held ticker makes the position unvaluable.
2. **A missing price is an error, never zero.** `formulas.total_value()` raises
   `ValuationUnavailableError`. Do not "helpfully" default it to 0.
3. **Every write takes the relevant lock** (`trade_lock`, `watchlist_lock`) for the full
   transaction — a trade is a read-validate-write sequence with await points in between, and
   without the lock two concurrent trades in the same process could interleave and lose an
   update. `Database.transaction()` adds a cross-instance advisory lock on top of it.
4. **`trades` is authoritative.** `positions` and `cash_balance` are a maintained projection.
5. **`change_percent` is not the daily change.** Use `daily_change_percent`, which is measured from
   `session_open`.
6. **There is no `DEFAULT_USER_ID`.** Every repository constructor requires a `user_id`; there is
   no default to fall back on. Services are built per request in `app/deps.py`, scoped to whichever
   user the session cookie resolves to — never build one without an explicit user id, in a test or
   otherwise.

## Market data API

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
from app.market import create_stream_router
from app.market.tickers import canonicalize_ticker, validate_ticker
```

- **`PriceUpdate`** — frozen dataclass: `ticker`, `price`, `previous_price`, `timestamp`,
  `session_open`, plus `change`, `change_percent`, `daily_change`, `daily_change_percent`,
  `direction`, and `to_dict()`.
- **`PriceCache`** — thread-safe. `update(ticker, price, timestamp=None, session_open=None)`,
  `get`, `get_price`, `get_all`, `remove`, and a monotonic `version` used for SSE change detection.
- **`MarketDataSource`** — `start(tickers)` → `add_ticker`/`remove_ticker` → `stop()`.
- **`create_market_data_source(cache)`** — Massive if `MASSIVE_API_KEY` is set, else the simulator.
  It takes no tuning arguments; `main.py` applies `SIM_SEED`, `SIM_TICK_MS`, and
  `SIM_VOL_MULTIPLIER` when constructing the simulator. The multiplier is the knob for visible
  demo movement — `SIM_TICK_MS` is not, since `dt` scales with it.
- **`create_stream_router(cache)`** — returns a fresh `APIRouter` mounting `GET /api/stream/prices`.

Default tickers, seed prices, and per-ticker volatility live in `app/market/seed_prices.py`.

## Testing

`tests/` mirrors `app/` one-to-one. Tests run against a real Postgres — `TEST_DATABASE_URL`
(defaults to `postgresql://trader:trader@localhost:5432/trader`, matching the compose service),
with each test getting its own throwaway schema, dropped afterward. Shared fixtures are in
`tests/conftest.py`:

| Fixture | What it gives you |
|---|---|
| `settings` | Settings pointed at a fresh throwaway schema, LLM mocked, seeded RNG |
| `db` / `seeded_db` | An initialized database in its own schema; `seeded_db` additionally seeds one known `TEST_USER_ID`, standing in for the first request that mints a guest — production seeds nothing at startup |
| `price_cache` / `priced_cache` | A bare cache, or one pre-filled at seed prices |
| `services` | Every service wired together against a stub market source, scoped to `TEST_USER_ID` |
| `api_client` | A `TestClient` over a fully started app (real lifespan) |

Service-level tests construct services directly rather than going through HTTP; reserve
`api_client` for route behaviour and integration.

## Reference

`planning/API_CONTRACT.md` is the frozen wire format. `planning/DECISIONS.md` explains why the
design is the way it is. `planning/BACKEND_SUMMARY.md` is the component handoff note.
