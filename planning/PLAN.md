# Trader — AI Trading Workstation

## Project Specification

## 1. Vision

Trader is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a native Apple app — the macOS/iOS register: system materials, system colours, light and dark as equals — with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A card-based trading aesthetic in the Apple system register, in whichever appearance their OS is set to
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

*Revised 2026-08-18: this section and §10 describe the Apple redesign. They replace the eToro
direction of the same date, which in turn replaced the original dark Bloomberg-terminal
direction. Both earlier passes are superseded on colour, typography, layout, and motion.*

Modelled on macOS and iOS: a system-native surface rather than a branded one. The density of a
professional tool is kept; the styling defers to the platform.

- **Two appearances, not one.** Light and dark are equal citizens, and `system` is the default —
  it follows the OS at load and keeps following it while the page is open. A header control
  overrides it. This is the single largest departure from every earlier direction, and it is
  what makes the app feel native rather than themed.
- **Materials, not panels.** The sidebar and the toolbar are translucent, blurred and
  saturation-boosted, so colour behind them shows through as tint rather than as grey. The
  workspace canvas carries two very soft radial tints purely so the blur has something to
  sample — a `backdrop-filter` over a flat fill is a no-op.
- **Continuous corners.** 10px on controls, 14px on cards, 20px on chrome. Where the browser
  supports `corner-shape`, these upgrade to real squircles; everywhere else the radii stand in.
- **Hairlines carry structure.** 0.5px separators, inset to the text edge inside a grouped list,
  so a run of rows reads as one group rather than as a stack of strips. Shadow is used sparingly
  in light and almost not at all in dark, where the elevated surface does that work.
- **Blue is interaction; green and red are direction.** systemBlue for selection, focus, links,
  and the prominent action. Green and red mean up and down — and, in the two places where the
  direction *is* the action, buy and sell. Nothing else competes.
- **Price flash animations**: brief green/red background tint on price change, fading over ~500ms
  via CSS animation. Its strength is a palette token rather than a constant, because at a 500ms
  tick rate almost every row is mid-animation at any moment, and the alpha that is a shimmer on
  white is a filled badge on black.
- **Connection status indicator**: a small colored dot *paired with a text label* (Live /
  Connecting / Reconnecting / Disconnected), visible in the header.
- **Data-dense but calm layout**: every pixel earns its place, but whitespace is allowed to
  do work.
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet and
  usable on a phone.

### Color Scheme

Apple's system colour set, defined once in `frontend/lib/theme.ts` as two complete palettes.
That file is the only place a colour literal appears; it emits the palettes two ways, and both
outputs are generated from the same token list so they cannot disagree:

- as a `:root` / `:root[data-theme="dark"]` stylesheet of **"R G B" channel triples**, injected
  into the document head, which Tailwind consumes as `rgb(var(--c-x) / <alpha-value>)` — the
  triple rather than a hex is what lets `bg-blue/15` keep working;
- as a plain object handed to the charts, because canvas and Recharts need a concrete colour at
  draw time and cannot read a custom property.

**Surfaces** — light / dark
- Canvas: `#F2F2F7` / `#000000` · Card: `#FFFFFF` / `#1C1C1E` · Sunk: `#EBEBF0` / `#2C2C2E`
- Separator: `#D8D8DC` / `#38383A` · Material tint: `#F6F6F8` / `#1C1C1E`, drawn at 72% through a blur

**Ink**
- Label: `#000000` / `#FFFFFF` · Secondary: `#5B5B60` / `#A1A1A6` · Faint: `#8E8E93` (both)
- Apple's own secondaryLabel resolves to about 3.0:1, which this app's floor does not allow, so
  the muted tone is darkened until it clears 4.5:1 on card and canvas alike.

**Blue — interaction, and only that**
- systemBlue `#007AFF` / `#0A84FF` · fill `#0071EB` / `#0A70DE` · text `#0040DD` / `#4DA3FF` · wash `#E5F1FF` / `#14304A`

**Direction**
- Up: `#34C759` / `#30D158` · fill `#1F7F33` / `#22883A` · text `#1E7A32` / `#30D158` · wash `#E4F8EA` / `#14301C`
- Down: `#FF3B30` / `#FF453A` · fill `#E02A20` / `#DE2A20` · text `#D70015` / `#FF453A` · wash `#FFE9E7` / `#3A1512`
- Flat: `#66666A` / `#98989D` · Caution (systemOrange): `#FF9500` / `#FF9F0A`, with its own text and wash

**Why each colour splits three ways.** A system colour is chosen to look right, not to carry
text: white on systemGreen is 2.2:1 and systemGreen on white is 1.9:1, so one token cannot do
both jobs. The base is used for anything that is not text — chart strokes, the flash tint, a
status dot, a heatmap cell. `*Fill` is darkened until a white label on it clears 4.5:1, for
buttons. `*Text` is darkened until it clears 4.5:1 as small text on a surface.
`__tests__/lib/theme.test.ts` holds every one of those pairings to the line in both appearances,
so the floor is enforced rather than asserted.

**Instrument identity colours.** With no logo assets, each symbol earns a stable colour instead,
hashed from the symbol itself (`instrumentColor(ticker, appearance)`). There are two sets: the
light hues are deep enough to carry white monogram ink, the dark ones bright enough to carry
near-black. None of them is systemBlue, systemGreen, or systemRed — those three are spoken for.
The same colour follows a holding through the watchlist chip, the positions table, the header's
allocation bar, and the main chart's line.

### Typography

- **One family: the system stack.** `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI
  Variable Text", …` resolves to genuine SF Pro on every Mac and iPhone, Segoe UI Variable on
  Windows, and the platform default elsewhere. SF Pro is not licensed for web self-hosting and
  is not on Google Fonts, so this is the only way to actually get it.
- **No second family, and no monospace.** Apple distinguishes by weight, size and tracking rather
  than by mixing faces. Body text is tracked at `-0.01em` and the portfolio value at `-0.03em`,
  because SF is drawn tighter than the web defaults it replaces.
- **All numerals are lining and tabular**, stated once on `body`, so a price moving from `$190.11`
  to `$190.98` does not shift its column. SF, Segoe UI Variable and Roboto all carry tabular
  figures, so this holds on every platform the stack resolves to.
- **Nothing is downloaded.** The export contains no font files, and the frontend build no longer
  needs network access to fetch any — removing a requirement the earlier directions imposed.


## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/trader.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
trader/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; trader.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/trader.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all watched tickers on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, and timestamp for each ticker
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server pushes price updates for all tickers known to the system at a regular cadence (~500ms) — in the single-user model this is equivalent to the user's watchlist
- Each SSE event contains ticker, price, previous price, timestamp, and change direction
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, and immediately after each trade execution.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment) |

---

## 9. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads recent conversation history from the `chat_messages` table
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "trader, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

---

## 10. Frontend Design

### Layout

The frontend is a single-page application shaped like a macOS app: a translucent sidebar, a
unified toolbar, and a three-column workspace where each panel owns its own scroll region. The
page itself does not scroll on a wide screen.

```
┌────────┬──────────────────────────────────────────────────┐
│ ▤ Trader │ PORTFOLIO VALUE  ALLOCATION      ● Live  ☀ ☾ ▭ │
│          │ $10,091.25 ▲ +$91.25  [██|██|░░]   cash        │
│ Watchlist├───────────┬──────────────────────┬─────────────┤
│ Markets  │ Watchlist │  Main chart          │  Assistant  │
│ Portfolio│  ⬤ AAPL   │                      │             │
│ Assistant│  ⬤ NVDA   ├──────────────────────┤   ╭───────╮ │
│          │  ⬤ MSFT   │  Trade ticket [S|B]  │   │bubble │ │
│          │           ├───────────┬──────────┤   ╰───────╯ │
│          │           │ Allocation│ Perform. │             │
│          │           ├───────────┴──────────┤             │
│          │           │  Positions           │             │
└────────┴───────────┴──────────────────────┴─────────────┘
```

Below the `lg` breakpoint this inverts: the sidebar collapses to a horizontal icon bar, panels
take their natural height, and the page scrolls as a whole, because a fixed viewport split four
ways leaves every panel too short to read.

The specific component architecture is up to the Frontend Engineer, but the UI should
include these elements:

- **Sidebar** — a macOS source list: translucent material, one row per workspace panel, each
  carrying that panel's live count (watchlist size, selected ticker, open positions) and
  scrolling it into view on the narrow layouts. Its labels are hidden below `lg`, which removes
  them from the accessibility tree too, so each row names itself on the button rather than
  relying on the text beside it.
- **Unified toolbar** — chrome rather than a card, wearing the same material as the sidebar.
  Carries the portfolio total value as the largest number on the page (updating live), unrealized
  P&L in currency and percent, cash balance, connection status, the **appearance control**, and a
  **segmented allocation bar**: one segment per holding, width by weight, each wearing that
  instrument's identity colour.
- **Appearance control** — a three-way segmented control (Light / Dark / System) in the toolbar.
  `system` is a first-class choice, not the absence of one: it keeps tracking the OS after load.
- **Watchlist panel** — a grouped inset list. One row per ticker: identity chip, symbol, company
  name, sparkline, live price (flashing green/red on change), and daily change % in a tinted
  pill. Separators are inset to the text edge; selection is a blue tint, and the row that is
  selected suppresses the separators around it so the tinted block reads as one boundary.
- **Main chart area** — larger chart for the currently selected ticker, price over time, headed
  by the instrument's chip, name, live price and change pill. The line takes the instrument's
  identity colour, so selecting a ticker recolours the chart to match the row that was clicked —
  and green stays reserved for "up".
- **Allocation & P&L heatmap** — treemap where each rectangle is a position, sized by portfolio
  weight, shaded by return (green = profit, red = loss). A cell prints its ticker and weight,
  adding the signed return once it is tall enough — on a freshly opened portfolio every return is
  ~0% and the weight is the number actually worth reading.
- **Performance chart** — area chart of total portfolio value over time, from
  `portfolio_snapshots`, headed by the session change.
- **Positions table** — ticker (with chip and company name), quantity, avg cost, current price,
  unrealized P&L, % change, on hairline separators.
- **Trade ticket** — labelled symbol field, units field, live order value, and Sell / Buy actions
  joined in a segmented track. They are two actions rather than two states of one choice, so each
  half stays its own button with its own direction fill; the track is only what says they are a
  pair. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar with an avatar, iOS message bubbles (the user's
  filled in the interaction colour, the assistant's in the neutral fill, each tightening its
  corner into a tail), suggested opening prompts as tinted capsules, and a loading indicator
  while waiting for the LLM. Trade executions and watchlist changes appear inline as receipts,
  carrying the instrument's chip and named in the tense that is true — a filled order reads
  "Bought 10 AAPL", a rejected one reads "Buy 10 AAPL".

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Canvas-based charting library preferred (Lightweight Charts or Recharts) for performance
- Price flash effect: derive the flash class during the render the price change already causes,
  and restart the CSS animation by remounting the node with a new key — no timer, no extra state,
  and no second render to clear the highlight
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling, with the token set of §2 defined once in `lib/theme.ts` and emitted
  both as CSS custom properties for Tailwind and as an object for the charts
- **The appearance reaches the charts through a store, not through CSS.** Custom properties
  already carry the palette to every styled element; the store exists for the three consumers
  that draw outside CSS — lightweight-charts into a canvas, Recharts into presentational SVG
  attributes, and the instrument chips, whose colour is per-symbol and so cannot be a variable.
  The canvas chart holds its colours rather than reading them, so a change of appearance rebuilds
  it.
- **The appearance is resolved before first paint.** The pages are prerendered, so a blocking
  script in `<head>` stamps `data-theme` from `localStorage` or the OS preference ahead of any
  styled element existing. The store adopts what that script already decided rather than deciding
  again during render — resolving it any earlier in React would make the client's first render
  disagree with the exported HTML.
- Canvas font strings cannot name a font stack the way CSS can, so charts read the resolved
  family off the document at mount
- Charts render timestamps in the viewer's local time; the series is keyed by UTC seconds, and an
  axis left on its default would put a different clock on one chart than on the one beside it
- Accessibility floor: colour is never the only encoding — every coloured number carries a sign
  and an arrow glyph; every foreground/background pairing the app renders small text in clears
  4.5:1 in **both** appearances, enforced by test rather than by eye; keyboard focus stays
  visible as the system blue halo; `prefers-reduced-motion` suppresses the flash and the
  page-load reveal

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v trader-data:/app/db -p 8000:8000 --env-file .env trader
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend writes `trader.db` to this path.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state, including that a rejected action is named in the
  tense that is true rather than reported as done
- Every coloured value carries its sign and arrow glyph, so meaning survives without colour
- The heatmap's colour scale, tested directly rather than through the charting library
- The palette itself: every foreground/background pairing the app renders small text in clears
  4.5:1 in both appearances, every instrument monogram clears it on its own chip, and the
  emitted stylesheet declares the same token set in both — so no token can silently fall back
  to the other appearance's value

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection

---

## 13. Review Questions, Clarifications & Simplifications

> **Status: resolved.** Every item below was answered during the build. The answers, with
> rationale, are in **`planning/DECISIONS.md`**, which is authoritative wherever it disagrees with
> this document. The wire format those decisions produced is frozen in
> **`planning/API_CONTRACT.md`**. This section is kept for provenance — read it to understand why
> a decision was made, not to decide anything.
>
> **One exception.** The *visual* answers here and in `DECISIONS.md` (notably D-48) predate both
> 2026-08-18 redesigns — the eToro pass and the Apple pass that replaced it — and still describe
> the dark `#0d1117` theme; see item #15 below. §2 and §10 of this document supersede them on
> colour, typography, layout, appearance handling, and motion. Everything non-visual in §13 and
> `DECISIONS.md` still stands.

Added 2026-08-17 by a documentation review pass. This section is advisory — it raises gaps that
two agents working in parallel (backend vs. frontend) would otherwise resolve differently. Items
marked **[decide]** need an answer before the relevant component is built; items marked
**[fix]** are internal contradictions in this document.

### 13.1 Contradictions in this document

1. **[fix] Docker volume style conflicts.** §4 says `db/` at the project root "maps to `/app/db`"
   (a bind mount), while §11 uses a *named* volume (`-v trader-data:/app/db`). With a named volume
   the repo's `db/.gitkeep` is inert and students cannot inspect or delete `trader.db` from the
   host. Recommend a bind mount (`-v "$(pwd)/db:/app/db"`) and deleting the named-volume wording.
2. **[fix] Browser launch.** §2 says "A browser opens to `http://localhost:8000`"; §11 says the
   start script "optionally opens the browser". Pick one (recommend: script opens it, with a flag
   to suppress).
3. **[fix] `.env` location.** §5 says the backend "reads `.env` from the project root", but §11
   passes `--env-file .env` to Docker, so inside the container there is no project-root `.env` to
   read. Simplify to: the backend reads **environment variables only**; `python-dotenv` loads
   `.env` for local (non-Docker) development.
4. **[fix] SSE event shape.** §6 says "Each SSE event contains ticker, price, previous price,
   timestamp, and change direction" (implying one event per ticker) and that the server pushes "at
   a regular cadence (~500ms)". The shipped implementation (`backend/app/market/stream.py`) sends
   **one event containing a map of all tickers**, and only when the cache version changes. Update
   §6 to the real contract before the frontend agent builds against it:
   ```
   retry: 1000

   data: {"AAPL": {"ticker","price","previous_price","timestamp","change","change_percent","direction"}, ...}
   ```

### 13.2 Market data ↔ watchlist ↔ positions coupling

5. **[decide] Who owns the tracked-ticker set?** The watchlist lives in SQLite; the price source
   keeps its own ticker list (`add_ticker`/`remove_ticker`). These must be reconciled on startup
   and on every watchlist mutation. Recommend stating explicitly: *the price source tracks
   `union(watchlist tickers, tickers with a non-zero position)`.*
6. **[decide] Removing a watched ticker you still hold.** §8's `DELETE /api/watchlist/{ticker}`
   would stop price updates for a ticker that still has an open position, which breaks portfolio
   valuation and the heatmap. Options: (a) refuse the delete with 409, (b) allow it but keep the
   ticker in the price source (per #5). Recommend (b).
7. **[decide] Trading an unwatched ticker.** The trade bar and the LLM can both name a ticker that
   isn't watched and therefore has no cached price. Specify: does a trade auto-add the ticker to
   the price source (and to the watchlist), or is it rejected with 400?
8. **[decide] Unknown / invalid tickers.** The simulator only has seed prices for known symbols and
   Massive will 404 on garbage input. What happens on `POST /api/watchlist {"ticker": "ZZZZ"}` or
   an LLM hallucinating a symbol? Needs: a validation rule, a synthetic seed price for unknown
   symbols in simulator mode, and a defined error body the chat flow can surface.
9. **[decide] Watchlist size cap.** The LLM can "manage the watchlist proactively" and could add
   40 symbols. In Massive mode that either blows the 5-calls/min free tier or forces a grouped
   endpoint. Suggest a documented cap (e.g. 25) plus a note on how Massive polls the union.
10. **[decide] Ticker canonicalization.** Uppercase + trim, enforced in exactly one place (a helper
    used by the REST route, the LLM action executor, and the seed data). Worth one sentence so the
    `UNIQUE(user_id, ticker)` constraint isn't defeated by `aapl` vs `AAPL`.

### 13.3 Missing data the UI is specified to display

11. **[decide] "Daily change %" has no source.** §10 requires a daily change % per watchlist row,
    but `PriceUpdate.previous_price` is the *previous tick*, not the session open or prior close.
    Something must supply a per-ticker baseline: the simulator can pin its seed price as the
    session open; Massive exposes previous close. Add a `session_open` (or `prev_close`) field to
    the price payload, or the number cannot be computed.
12. **[decide] The main chart starts empty.** §2 says sparklines accumulate on the frontend since
    page load, and §10 gives the main chart "price over time" with no stated source — so on a
    fresh reload the "larger detailed chart" renders nothing for the first several seconds. Either
    state that plainly, or add a bounded server-side ring buffer (e.g. last 600 ticks/ticker,
    in-memory) behind `GET /api/history/{ticker}` so charts have immediate shape. Recommend the
    ring buffer: ~20 lines of code, and it removes the worst first-impression problem in the demo.
13. **[decide] No chat history endpoint.** `chat_messages` is persisted, but §8 has no
    `GET /api/chat`, so a page reload shows an empty conversation while the DB quietly grows. Add
    the GET, or drop the table and keep chat in memory.
14. **[decide] `GET /api/portfolio/history` has no parameters.** Define the query contract
    (`?limit=`, `?since=`, or a fixed "last N points") and the max points returned, so the P&L
    chart isn't fetching an unbounded array after a long-running container.
15. **[decide] Up/down colors are undefined.** §2 fixes yellow/blue/purple but never names the
    green and red used for ticks, P&L, and the heatmap scale — the three most-used colors in the
    app. Add explicit tokens (up, down, neutral/flat, plus the heatmap gradient endpoints) and
    check contrast against `#0d1117`.
    *Answered by §2 as rewritten: each direction colour splits into a base, a `*Fill` and a
    `*Text` variant, in two appearances, and the contrast check is a test rather than a one-off.*
16. **[decide] Timestamp format is inconsistent.** Prices use Unix float seconds (`time.time()`);
    every DB column uses ISO-8601 strings. Pick one representation for **JSON responses** — ISO-8601
    UTC everywhere is the safer default — and state it, or the frontend will need two parsers.

### 13.4 Portfolio & trade semantics

17. **[decide] Position lifecycle on a full sell.** Does the `positions` row get deleted, or kept
    with `quantity = 0`? §12's E2E scenario hedges ("updates or disappears"). Recommend: delete
    when `quantity` falls below an epsilon (e.g. `1e-9`), which also prevents float dust rows.
18. **[decide] Float rounding rules.** Fractional shares plus `REAL` cash means "sell everything"
    can leave a residual position of `2e-14` or push cash to `-0.0000001`. Specify rounding at the
    boundary: cash to 2dp, quantity to 6dp, comparisons via epsilon.
19. **[decide] Realized P&L is never stored.** Only unrealized P&L is specified. The `trades` log
    makes realized P&L derivable, but nothing displays it and no field holds it. Is realized P&L in
    scope for the positions table / header? (If not, say so — otherwise an agent will add it.)
20. **[decide] Trade validation edge cases** to enumerate once, so manual and LLM trades share
    them: quantity must be > 0 and finite; ticker must have a cached price (otherwise 409, not a
    fill at price 0); no short selling; `buy` with insufficient cash → 400 with a machine-readable
    `code` the chat flow can relay; stale-price tolerance in Massive mode (a 15s-old quote fills at
    that quote — confirm that's acceptable).
21. **[decide] Source of truth: `trades` vs `positions`/`cash_balance`.** The latter two are
    derivable from the former. Keeping them is the right call for query simplicity, but state that
    `trades` is authoritative and that positions/cash are a maintained projection — so a future
    "recompute from trades" repair is well-defined.
22. **[decide] `portfolio_snapshots` growth.** A row every 30s is ~2,880/day forever, with no
    retention policy and no snapshot at t=0 (so the P&L chart is empty for the first 30 seconds).
    Recommend: write one snapshot at DB init, and cap the table (delete rows older than N days, or
    keep the newest N rows) inside the same background task.

### 13.5 LLM integration

23. **[decide] Conversation history window.** "Recent conversation history" is unbounded as
    written. Specify a limit (e.g. last 20 messages, truncated by characters) — it bounds both cost
    and latency.
24. **[decide] LLM failure behavior.** What does `POST /api/chat` return when OpenRouter is down,
    rate-limits, times out, or returns unparseable JSON? A 502 forces the frontend to invent an
    error bubble; returning a normal shape with a friendly `message` and an `error` flag keeps the
    chat panel simple. Also specify a request timeout and whether one retry is attempted.
25. **[decide] Structured-output support on this provider path.** §9 pins
    `openrouter/openai/gpt-oss-120b` with Cerebras. Confirm that strict JSON-schema
    `response_format` is honored on that route (via the cerebras-inference skill) and document the
    fallback — json_object mode plus a parse-and-repair retry — because a schema failure otherwise
    breaks the headline feature.
26. **[decide] `LLM_MOCK` contract is unspecified.** §12 requires an E2E test where "trade
    execution appears inline" under mock mode, which is only possible if the mock keys off the
    input text. Define the mapping in this document (e.g. a message matching `/buy (\d+) (\w+)/i`
    returns a trade action; anything else returns a canned analysis message), otherwise the backend
    and E2E agents will write incompatible halves.
27. **[decide] Partial action failure.** If the LLM returns three trades and the second fails
    validation, are the other two still executed, and does the stored `actions` JSON record the
    failure? Recommend: execute independently, record per-action `status`/`error`, surface all of
    it in the response.

### 13.6 Runtime & operational details

28. **[decide] SQLite concurrency.** Two background tasks (price source, snapshot writer) plus
    request handlers will touch the DB from different threads/tasks. State the approach: WAL mode
    on, `check_same_thread=False`, and either `aiosqlite` or `run_in_threadpool` for writes from
    async routes. Left unstated, "database is locked" will show up under E2E load.
29. **[decide] Port binding.** The app has no auth and auto-executes trades. `-p 8000:8000` exposes
    it on the LAN; `-p 127.0.0.1:8000:8000` doesn't. Recommend localhost-only in the start scripts.
30. **[decide] `/api/health` payload.** Make it useful: market source in use (`simulator`/`massive`),
    seconds since the last price tick, tracked-ticker count, DB reachable. E2E can then wait on a
    real readiness signal instead of sleeping.
31. **[decide] Massive mode outside market hours.** Real quotes go static overnight and on
    weekends, so the app looks frozen and the "price flash" feature never fires. Document the
    expected behavior (and consider falling back to the simulator when quotes are stale beyond a
    threshold).
32. **[decide] Deterministic simulator for tests.** Add a `SIM_SEED` (and optionally
    `SIM_TICK_MS`) env var. E2E assertions about price movement are otherwise inherently flaky, and
    §12's "SSE resilience: disconnect and verify reconnection" needs a stated mechanism for forcing
    the disconnect (CDP offline emulation vs. restarting the container).
33. **[decide] No reset path.** A demo app that auto-executes trades needs a way back to $10k.
    Suggest `POST /api/reset` (also the cleanest per-test fixture for E2E) or a documented "delete
    `db/trader.db` and restart".

### 13.7 Opportunities to simplify

34. **Replace the four platform scripts with `docker compose up/down`.** §4 lists
    `start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1` *and* an optional
    `docker-compose.yml` — five artifacts, two code paths, four files to keep in sync. Compose
    works identically on macOS, Linux, and Windows. Keep the scripts only as one-line wrappers
    (`docker compose up -d --build && open http://localhost:8000`) so the platform-specific logic
    exists in one place.
35. **Make `GET /api/watchlist` return tickers only, not "with latest prices".** Prices already
    arrive over SSE. Serving them twice gives the frontend two sources of truth for the same value
    and a visible flicker when the REST snapshot is staler than the stream. The one exception is
    the very first paint — which is better solved by the ring buffer in #12.
36. **Fold `POST /api/watchlist` + `DELETE` semantics into the union rule (#5)** so watchlist
    mutation is a pure DB write plus one reconcile call, rather than bespoke logic in three places
    (REST route, LLM executor, startup).
37. **Add an `API_CONTRACT.md` under `planning/`** — request/response JSON for every endpoint, the
    SSE payload, and the error envelope — and make it the single file the frontend agent reads.
    Right now those shapes are spread across §6, §8, and §9 in prose, which is the most likely
    source of frontend/backend drift in a parallel agent build. This is the highest-leverage item
    in this section.
38. **Define one error envelope** (e.g. `{"error": {"code": "INSUFFICIENT_CASH", "message": "..."}}`)
    used by every route. The chat flow, the trade bar, and the E2E tests all need to distinguish
    error kinds; without a shared shape each will string-match.
39. **Consider dropping `chat_messages` persistence** if #13 lands on "no history endpoint" — an
    in-memory deque removes a table, a schema section, and a growth concern. (Keep it if reload
    persistence is wanted; just make the choice explicit.)
40. **Mark §12's market-data test bullets as done.** `planning/MARKET_DATA_SUMMARY.md` records 73
    passing tests covering exactly those items; leaving them as open work invites a duplicate pass.

### 13.8 Smaller questions

41. Does the header's "portfolio total value" update on every SSE tick (recomputed client-side from
    positions × live prices), or only on `GET /api/portfolio`? Client-side is the only way to get
    the "updating live" feel described in §10 — worth stating.
42. Is the chat panel's collapse state, the selected ticker, or any other UI state persisted across
    reloads (localStorage), or is it all ephemeral?
43. Is there any protection against a double-clicked buy button submitting twice? (Probably out of
    scope for a fake-money demo — but say so, or an agent will build idempotency keys.)
44. §1 says "Agents interact through files in `planning/`", but no roster of agents or handoff
    file-naming convention is defined; `MARKET_DATA_SUMMARY.md` is currently the only example of
    the pattern. Consider documenting the convention (one `*_SUMMARY.md` per completed component,
    archives under `planning/archive/`) so later agents follow it without being told.
