# API_CONTRACT.md

**Status: frozen.** This is the single file the frontend builds against. If an implementation
disagrees with this document, the implementation is wrong. Changes require updating this file and
both sides in the same commit.

Conventions:
- Base URL is same-origin. Every path below is prefixed by the app root (`http://localhost:8000`).
- All request and response bodies are `application/json`, except the SSE stream.
- **Timestamps in JSON bodies are ISO-8601 UTC strings** (`2026-08-18T09:14:03Z`).
  **Timestamps in the SSE payload are Unix float seconds.** These are the only two formats; the
  frontend converts at exactly one place, the SSE parse boundary. (DECISIONS D-27)
- Money is a JSON number rounded to 2 decimal places. Quantities are rounded to 6.
- `user_id` is always `"default"` and never appears in a request or response body.

---

## 1. Error envelope

Every non-2xx response from every endpoint has exactly this shape (DECISIONS D-23):

```json
{"error": {"code": "INSUFFICIENT_CASH", "message": "Need $1,900.00 but only $1,000.00 available."}}
```

`code` is machine-readable and drawn from the closed set below. `message` is human-readable and
safe to display verbatim. No other top-level keys.

| Code | HTTP | Meaning |
|---|---|---|
| `INVALID_TICKER` | 400 | Not 1–5 letters after trim + uppercase |
| `INVALID_QUANTITY` | 400 | Not finite, or ≤ 0 |
| `INSUFFICIENT_CASH` | 400 | Buy cost exceeds cash balance |
| `INSUFFICIENT_SHARES` | 400 | Sell quantity exceeds held quantity (no short selling) |
| `WATCHLIST_FULL` | 400 | Watchlist already holds 25 tickers |
| `TICKER_NOT_FOUND` | 404 | Ticker is not on the watchlist / has no history |
| `PRICE_UNAVAILABLE` | 409 | No cached price yet; the trade is refused rather than filled at 0 |
| `VALIDATION_ERROR` | 422 | Request body failed schema validation |
| `VALUATION_UNAVAILABLE` | 500 | A held position has no cached price, so the portfolio cannot be valued |
| `INTERNAL_ERROR` | 500 | Unexpected failure; details are logged, never returned |

`POST /api/chat` is the one endpoint that does **not** use this envelope for upstream LLM failures —
see §7.

---

## 2. SSE — `GET /api/stream/prices`

Long-lived `text/event-stream`. The client uses native `EventSource` and relies on its built-in
reconnect. Response headers: `Cache-Control: no-cache`, `Connection: keep-alive`,
`X-Accel-Buffering: no`.

Frame sequence:

```
retry: 1000

data: {"AAPL": { ...PriceSnapshot... }, "MSFT": { ...PriceSnapshot... }}

: keepalive

data: {"AAPL": { ... }, "MSFT": { ... }}
```

- **One `data:` frame contains a map of every tracked ticker.** It is not one event per ticker.
- Frames are emitted only when the server's price cache version changes, polled every 500ms.
- `: keepalive` comment frames are sent after 15s without a data frame. `EventSource` ignores them;
  they exist to stop idle proxies dropping the connection.
- There is no `event:` name, so the client uses `onmessage`, not `addEventListener("...")`.

### PriceSnapshot

```json
{
  "ticker": "AAPL",
  "price": 191.24,
  "previous_price": 191.19,
  "timestamp": 1755500000.123,
  "session_open": 190.00,
  "change": 0.05,
  "change_percent": 0.0262,
  "daily_change": 1.24,
  "daily_change_percent": 0.6526,
  "direction": "up"
}
```

| Field | Type | Meaning |
|---|---|---|
| `price` | number | Latest price, 2dp |
| `previous_price` | number | Price at the **previous tick** (~500ms ago) |
| `timestamp` | number | Unix seconds, float |
| `session_open` | number | Session baseline: the simulator's seed price, or Massive's previous close |
| `change` / `change_percent` | number | Movement since the previous **tick**. Near zero. Drives the flash animation only. |
| `daily_change` / `daily_change_percent` | number | Movement since `session_open`. **This is the number the UI labels "daily change %".** |
| `direction` | `"up"` \| `"down"` \| `"flat"` | Tick direction. Drives flash color. |

> Do not display `change_percent` as the daily change. They are different numbers and confusing them
> is the single most likely integration bug in this app.

---

## 3. Portfolio

### `GET /api/portfolio`

```json
{
  "cash_balance": 8100.00,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 10.0,
      "avg_cost": 190.00,
      "current_price": 191.24,
      "market_value": 1912.40,
      "unrealized_pnl": 12.40,
      "pct_change": 0.6526
    }
  ],
  "positions_value": 1912.40,
  "total_value": 10012.40,
  "unrealized_pnl": 12.40
}
```

`pct_change` on a position is return since acquisition, `(current_price - avg_cost) / avg_cost * 100`
— **not** the daily change. If any held ticker has no cached price the whole request fails with
`VALUATION_UNAVAILABLE`; positions are never valued at 0.

### `POST /api/portfolio/trade`

Request:
```json
{"ticker": "AAPL", "side": "buy", "quantity": 10}
```
`side` is `"buy"` or `"sell"`. `quantity` supports fractional shares.

Response `200`:
```json
{
  "trade": {
    "id": "3f2a...",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 10.0,
    "price": 191.24,
    "executed_at": "2026-08-18T09:14:03Z"
  },
  "cash_balance": 8087.60,
  "position": {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 191.24},
  "realized_pnl": null,
  "total_value": 10012.40
}
```

- Market order, instant fill, no fees, no confirmation.
- Fill price is the cached price read once immediately before execution. A quote up to one poll
  interval old fills at that quote (DECISIONS D-20).
- `position` is `null` when a sell closes the position entirely.
- `realized_pnl` is populated on sells and `null` on buys. It is computed, never stored.
- Trading a ticker that is not on the watchlist **auto-adds it** to the watchlist and the price
  source (DECISIONS D-05). If no price is cached yet, the trade fails with `PRICE_UNAVAILABLE`
  rather than filling at 0.
- Validation order and error codes: `INVALID_TICKER` → `INVALID_QUANTITY` → `PRICE_UNAVAILABLE` →
  `INSUFFICIENT_CASH` / `INSUFFICIENT_SHARES`.

### `GET /api/portfolio/history?limit=500`

`limit` defaults to 500, capped at 5000. Ordered oldest-first for direct charting.

```json
{"snapshots": [{"total_value": 10000.00, "recorded_at": "2026-08-18T09:00:00Z"}]}
```

A snapshot is written at database init, every 30 seconds, and immediately after every trade. Rows
older than 7 days are pruned.

---

## 4. Watchlist

### `GET /api/watchlist`

```json
{"tickers": ["AAPL", "GOOGL", "MSFT"], "cap": 25}
```

Ordered by `added_at` ascending — the frontend renders in exactly this order and never derives row
order from the SSE map. **No prices are returned**; prices come from SSE only (DECISIONS D-24).

### `POST /api/watchlist`

Request `{"ticker": "pypl"}` — canonicalized server-side. Idempotent: adding an existing ticker
returns 200 and changes nothing.

Response `200`: `{"tickers": ["AAPL", "...", "PYPL"], "cap": 25}`

Errors: `INVALID_TICKER`, `WATCHLIST_FULL`.

### `DELETE /api/watchlist/{ticker}`

Response `200`: `{"tickers": [...], "cap": 25}`. Errors: `INVALID_TICKER`, `TICKER_NOT_FOUND`.

Removing a ticker you still hold is **allowed**. The watchlist row is deleted but the price feed
continues, because the price source tracks `union(watchlist, tickers with an open position)`
(DECISIONS D-01/D-02/D-03). The position remains visible in the positions table and heatmap.

---

## 5. Price history — `GET /api/history/{ticker}`

Seeds charts on first paint so they are not empty after a reload.

```json
{
  "ticker": "AAPL",
  "points": [{"timestamp": 1755500000.123, "price": 190.02}]
}
```

Up to the last 600 ticks, oldest-first, held in memory only — the buffer is empty after a restart
and is cleared by `POST /api/reset`. `timestamp` is Unix float seconds, matching the SSE payload.
A ticker that has never been tracked returns `TICKER_NOT_FOUND`; a tracked ticker with no ticks yet
returns an empty `points` array.

---

## 6. Chat

### `GET /api/chat?limit=50`

```json
{
  "messages": [
    {
      "id": "9c1e...",
      "role": "user",
      "content": "buy 10 AAPL",
      "actions": null,
      "created_at": "2026-08-18T09:14:00Z"
    },
    {
      "id": "a77b...",
      "role": "assistant",
      "content": "Bought 10 AAPL at $191.24.",
      "actions": [
        {
          "kind": "trade",
          "ticker": "AAPL",
          "status": "ok",
          "detail": {"side": "buy", "quantity": 10.0, "price": 191.24},
          "error_code": null,
          "error_message": null
        }
      ],
      "created_at": "2026-08-18T09:14:02Z"
    }
  ]
}
```

Oldest-first. `actions` is `null` on user messages and an array on assistant messages.

### `POST /api/chat`

Request: `{"message": "buy 10 shares of AAPL"}`

Response `200`:
```json
{
  "message": "Bought 10 AAPL at $191.24. That is 19% of your portfolio in one name.",
  "actions": [
    {"kind": "trade", "ticker": "AAPL", "status": "ok",
     "detail": {"side": "buy", "quantity": 10.0, "price": 191.24},
     "error_code": null, "error_message": null}
  ],
  "error": false
}
```

- `kind` is `"trade"` or `"watchlist"`. `status` is `"ok"` or `"error"`.
- Actions execute **independently**. If the LLM returns three trades and the second fails
  validation, the other two still execute and all three appear in `actions` with their own status
  (DECISIONS D-32).
- Trades from chat go through exactly the same validation as manual trades.

---

## 7. LLM failure behavior

When the upstream model is unreachable, times out, rate-limits, or returns unparseable JSON after
one repair retry, `POST /api/chat` still returns **HTTP 200** with the normal body shape
(DECISIONS D-31):

```json
{
  "message": "I'm having trouble reaching the AI assistant right now. Your portfolio is unchanged.",
  "actions": [],
  "error": true
}
```

The frontend renders `error: true` messages as a normal assistant bubble with a warning affordance.
It never needs a separate error path for chat. Request timeout is 30 seconds with one retry.

---

## 8. System

### `GET /api/health`

```json
{
  "status": "ok",
  "market_source": "simulator",
  "seconds_since_last_tick": 0.31,
  "tracked_tickers": 10,
  "db_ok": true
}
```

`status` is `"ok"` or `"degraded"`. `market_source` is `"simulator"` or `"massive"`.
`seconds_since_last_tick` is `null` before the first tick. E2E waits on this instead of sleeping.

### `POST /api/reset`

Restores the seeded state: $10,000 cash, the ten default tickers, no positions, no trades, no chat
history, cleared price history, one fresh snapshot. Returns the same body as `GET /api/portfolio`.

---

## 9. LLM mock mode

With `LLM_MOCK=true` the backend never calls OpenRouter and responds deterministically from the
user's message text. Backend and E2E both build against this table (DECISIONS D-33):

| Message matches | Response |
|---|---|
| `/\b(buy\|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares\s+of\s+)?([A-Za-z]{1,5})\b/i` | Confirmation text + one matching trade action |
| `/\b(add\|remove)\s+([A-Za-z]{1,5})\b.*watchlist/i` | Confirmation text + one matching watchlist action |
| `/\b(portfolio\|position\|holding)/i` | Portfolio analysis quoting real context values, no actions |
| contains `__mock_error__` | The failure response from §7, `error: true` |
| anything else | Canned analysis message, no actions |

---

## 10. Design tokens

Defined once in `frontend/lib/theme.ts` and imported by both the Tailwind config and the canvas
chart code, which cannot read CSS custom properties at draw time.

| Token | Value | Use |
|---|---|---|
| `bg` | `#0d1117` | Page background |
| `bgAlt` | `#161b22` | Panel background |
| `border` | `#30363d` | Panel borders |
| `accentYellow` | `#ecad0a` | Highlights, selected row |
| `accentBlue` | `#209dd7` | Links, chart line |
| `accentPurple` | `#753991` | Submit buttons |
| `up` | `#22c55e` | Uptick, profit |
| `upText` | `#4ade80` | Small profit text (contrast at small sizes) |
| `down` | `#ef4444` | Downtick, loss |
| `downText` | `#f87171` | Small loss text |
| `flat` | `#9ca3af` | Unchanged, muted |
| `heatmapLossDeep` | `#7f1d1d` | Treemap loss extreme |
| `heatmapNeutral` | `#374151` | Treemap zero |
| `heatmapProfitDeep` | `#14532d` | Treemap profit extreme |

**Color is never the only encoding** (DECISIONS D-48). Every P&L and direction value pairs its color
with a glyph and an explicit sign: `▲ +0.65%`, `▼ -1.10%`. Heatmap cells always carry a signed
percentage label. The connection dot always carries a text label.
