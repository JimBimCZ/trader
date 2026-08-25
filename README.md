# Trader — AI Trading Workstation

A visually dense trading terminal: live streaming prices, a simulated $10,000 portfolio, and an
LLM assistant that can analyze your positions and execute trades on your behalf.

The app itself runs in one container on one port — `docker compose` also starts a companion
Postgres. No login, no signup, no real money.

![Trader](docs/screenshot.png)

## Quick start

```bash
cp .env.example .env      # add your OPENROUTER_API_KEY
./scripts/start_mac.sh    # macOS/Linux  (scripts\start_windows.ps1 on Windows)
```

`docker compose up` starts two containers: the app and a local Postgres. The app opens at
<http://localhost:8000>. To stop it:

```bash
./scripts/stop_mac.sh
```

Both scripts wrap `docker compose`, so `docker compose up -d --build` and `docker compose down`
work identically if you prefer.

Your portfolio persists in the `trader-pgdata` Docker volume between restarts. `docker compose
down -v` wipes that volume and starts you over at $10k; the in-app reset still works too.

The app is multi-user, but there is still no sign-in (that's a later phase). The first request a
browser makes mints an anonymous guest and points a signed `trader_session` cookie at it; every
later request from that browser resolves back to the same row. Two browsers get two independent
$10k portfolios from the same running app. Clear cookies, or lose the cookie some other way, and
that guest's data is unreachable — there is no password or email to recover it with.

## What you can do

- **Watch prices stream** — the watchlist updates twice a second, flashing green on an uptick and
  red on a downtick, with a sparkline building up beside each row.
- **Chart a ticker** — click any watchlist row. The chart seeds from the server's history buffer so
  it has shape immediately, then follows the stream live.
- **Trade** — ticker, quantity, buy or sell. Market orders, instant fill, no fees, no confirmation.
- **Watch your portfolio** — a treemap sized by position weight and coloured by P&L, a portfolio
  value chart, and a positions table with live return figures.
- **Talk to the assistant** — "how is my portfolio doing?", "buy 10 AAPL", "add PYPL to my
  watchlist". It executes trades directly, and shows each one inline as it happens.

## Configuration

All configuration is environment variables. `.env` is read for local development; Docker passes it
with `--env-file`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | — | Postgres connection string. The app refuses to start without one — `docker compose` supplies the local Postgres service's URL automatically; a manual `uv run uvicorn` needs it set by hand. |
| `OPENROUTER_API_KEY` | For real chat | — | OpenRouter key. Without it the assistant falls back to mock responses. |
| `MASSIVE_API_KEY` | No | empty | Set to use real market data from Massive/Polygon. **Leave empty to use the built-in simulator**, which costs nothing and works offline. |
| `LLM_MOCK` | No | `false` | `true` gives deterministic assistant responses with no API calls. Used by the E2E suite. |
| `SIM_SEED` | No | unset | Seeds the simulator's RNG, making price paths reproducible. |
| `SIM_TICK_MS` | No | `500` | Simulator tick interval. The GBM time step is derived from it, so a faster tick gives proportionally smaller moves, not livelier ones. |
| `SIM_VOL_MULTIPLIER` | No | `1.0` | Scales simulated volatility. `1.0` is realistic — and realistic means cents per second, which looks static in a short demo. Try `25` for visibly moving prices, `100` for dramatic. |
| `MASSIVE_POLL_SECONDS` | No | `15` | Massive poll interval. The default suits the free tier's 5 calls/minute. |
| `SESSION_SECRET` | **Yes, in production** | a random value, regenerated every restart | Signs the `trader_session` cookie that is the only pointer to a guest's row. Leave it unset and it works for local dev, but **every restart mints a new secret, which invalidates every existing cookie and permanently orphans every guest's portfolio** — the row is still in Postgres, but nothing can ever prove which cookie pointed at it again. Set it to a fixed random string before deploying. |
| `GUEST_TTL_DAYS` | No | `7` | Days of inactivity (`last_seen_at`) after which a guest account — and everything that cascades from it: watchlist, positions, trades, chat — is deleted. |
| `CLEANUP_SECRET` | No | empty | Shared secret required (as the `X-Cleanup-Secret` header) to call `POST`/`GET /api/admin/cleanup`, which deletes guests past `GUEST_TTL_DAYS`. Unset, the route refuses every call — the safe default for an endpoint that deletes rows. |

### Market data

By default prices come from a geometric Brownian motion simulator with per-ticker volatility,
correlated sector moves, and occasional 2–5% shocks. It needs no API key and no network.

Out of the box it is calibrated to real volatility, which over a few seconds means sub-cent moves —
accurate, but it can look frozen when you are demoing. `SIM_VOL_MULTIPLIER=25` makes the movement
obvious without changing anything else about the model.

With `MASSIVE_API_KEY` set, prices come from real market data instead. Outside market hours real
quotes are static, so the display will look frozen and the flash animation will not fire. That is
expected — there is deliberately no automatic fallback to the simulator, because silently swapping
real data for synthetic data is worse than a still screen.

## Architecture

```
Docker container (port 8000)                 ──►  Postgres 16
├── FastAPI                                       (compose service locally,
│   ├── /api/*          REST                       Neon when deployed)
│   ├── /api/stream/*   Server-Sent Events
│   └── /*              the exported frontend
└── Background tasks: market data, history collection, portfolio snapshots, guest cleanup
```

- **Frontend** — Next.js + TypeScript, built as a static export and served by FastAPI. One origin,
  so no CORS.
- **Backend** — FastAPI, managed with `uv`.
- **Real-time** — SSE rather than WebSockets: the data only flows one way.
- **LLM** — LiteLLM → OpenRouter → `openai/gpt-oss-120b` on Cerebras, with structured outputs.

## Development

```bash
# Backend
cd backend
uv sync --extra dev
uv run --extra dev pytest                  # 492 tests, needs Postgres (TEST_DATABASE_URL, defaults to the compose service)
uv run --extra dev ruff check app/ tests/
uv run uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm test                                   # 56 tests
npm run dev

# E2E (needs Docker)
cd test
npm install && npx playwright install chromium
docker compose -f docker-compose.test.yml up -d --build
npx playwright test
```

To run the frontend against the backend during development, build it once (`npm run build`) and
point the backend at it with `STATIC_DIR=../frontend/out`.

## Deploying to Vercel

Docker is the reference deployment. The app also runs on Vercel, where a long-lived process is not
available: prices there are computed from the clock rather than ticked by a background task. Both
targets run on Postgres — the compose service locally, Neon when deployed — behind the same
interface, so the routes, services and frontend are identical on either target.

The repository root carries `vercel.json`, `requirements.txt` and `api/index.py`; pushing to `main`
deploys. `DATABASE_URL` must be set to a Neon **pooled** connection string before the deployment is
usable — there is no fallback database, so the app refuses to start without one. Set `SESSION_SECRET`
too, or every cold start regenerates it and orphans every existing guest. `vercel.json` schedules a
daily Cron hit against `/api/admin/cleanup`, but as shipped that hit cannot yet authenticate itself
(Vercel Cron has no way to attach the required header) — see `planning/VERCEL_DEPLOYMENT.md` for
the detail, including this gap.

## Documentation

| Document | What it is |
|---|---|
| `planning/API_CONTRACT.md` | The wire format. Frozen: every endpoint, the SSE payload, the error envelope. |
| `planning/VERCEL_DEPLOYMENT.md` | The serverless target: what changed, why, and how to finish the setup. |
| `planning/DECISIONS.md` | Resolved design decisions, and why. Authoritative over `PLAN.md`. |
| `planning/PLAN.md` | The original product brief. |
| `planning/REVIEW.md` | A review pass that audited the plan against the shipped code. |
| `backend/CLAUDE.md` | Backend developer guide. |

## Safety note

The app has no sign-in — every visitor is an anonymous guest, minted automatically — and executes
trades without confirmation, so the container binds to `127.0.0.1` only. It is a demo with
imaginary money and no way to prove who a guest is beyond holding their cookie; do not expose it to
a network. See `SESSION_SECRET` above for the sharpest consequence of running it unconfigured.
