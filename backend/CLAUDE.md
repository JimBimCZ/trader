# Backend — Developer Guide

FastAPI application serving the REST API, the SSE price stream, and the exported frontend.

## Setup

```bash
cd backend
uv sync --extra dev
```

## Commands

```bash
uv run --extra dev pytest                      # 314 tests
uv run --extra dev pytest --cov=app            # with coverage (97%)
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
| `app/deps.py` | FastAPI dependencies, resolved from `app.state` |
| `app/reconcile.py` | Owns the tracked-ticker set |
| `app/db/` | Schema, connection, seed |
| `app/market/` | Simulator, Massive client, price cache, SSE |
| `app/portfolio/` | Trades, valuation, snapshots |
| `app/watchlist/` | Watchlist CRUD |
| `app/history/` | In-memory price ring buffer |
| `app/llm/` | Chat, structured outputs, mock client |
| `app/system/` | Health and reset |

Each domain is repository → service → router. Logic goes in the service, SQL in the repository,
HTTP translation only in the router.

## Invariants worth knowing before you change anything

1. **Only `reconcile.py` may call `source.remove_ticker()`.** It also evicts the cached price, so
   calling it for a held ticker makes the position unvaluable.
2. **A missing price is an error, never zero.** `formulas.total_value()` raises
   `ValuationUnavailableError`. Do not "helpfully" default it to 0.
3. **Every write takes the relevant lock** (`trade_lock`, `watchlist_lock`) for the full
   transaction. aiosqlite serializes statements, not transactions.
4. **`trades` is authoritative.** `positions` and `cash_balance` are a maintained projection.
5. **`change_percent` is not the daily change.** Use `daily_change_percent`, which is measured from
   `session_open`.

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
  It takes no tuning arguments; `main.py` applies `SIM_SEED` and `SIM_TICK_MS` when constructing
  the simulator.
- **`create_stream_router(cache)`** — returns a fresh `APIRouter` mounting `GET /api/stream/prices`.

Default tickers, seed prices, and per-ticker volatility live in `app/market/seed_prices.py`.

## Testing

`tests/` mirrors `app/` one-to-one. Shared fixtures are in `tests/conftest.py`:

| Fixture | What it gives you |
|---|---|
| `settings` | Settings on a temp database, LLM mocked, seeded RNG |
| `db` / `seeded_db` | An initialized (and optionally seeded) database |
| `price_cache` / `priced_cache` | A bare cache, or one pre-filled at seed prices |
| `services` | Every service wired together against a stub market source |
| `api_client` | A `TestClient` over a fully started app (real lifespan) |

Service-level tests construct services directly rather than going through HTTP; reserve
`api_client` for route behaviour and integration.

## Reference

`planning/API_CONTRACT.md` is the frozen wire format. `planning/DECISIONS.md` explains why the
design is the way it is. `planning/BACKEND_SUMMARY.md` is the component handoff note.
