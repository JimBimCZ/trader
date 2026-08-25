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
- `user_id` never appears in a request or response body. The caller is resolved server-side from
  the `trader_session` cookie (§0) on every request; there is no way to name a user id on the wire.

---

## 0. Identity — the `trader_session` cookie

*Corrected 2026-08-25.* Sign-in exists and is optional — see §0.1. What follows describes what
happens to every request regardless of whether the caller ever signs in: a route other than the
ones named below resolves a caller from a signed cookie, minting a fresh guest the first time a
browser arrives without one (or with one that no longer verifies — see below). Nothing about this
is visible in a request or response body; it is entirely a `Set-Cookie` / `Cookie` exchange.

| Attribute | Value |
|---|---|
| Name | `trader_session` |
| Contents | The user id, signed (itsdangerous `URLSafeTimedSerializer`); opaque to the client |
| `Max-Age` | `7776000` seconds (90 days), **sliding** — see below |
| `HttpOnly` | yes |
| `SameSite` | `Lax` |
| `Secure` | Set when the request reached the app over https — judged from `X-Forwarded-Proto` when present (so a TLS-terminating proxy like Vercel is honored), falling back to the request's own scheme otherwise. **Not** decided by hostname: a Docker deployment reached over plain http on a LAN address must not get a `Secure` cookie, or the browser silently refuses to store it and mints a fresh guest on every request. |
| `Path` | `/` |

A cookie that fails to verify — tampered, signed under a rotated `SESSION_SECRET`, or pointing at a
row a database reset removed — is treated exactly like no cookie at all: a fresh guest is minted
rather than the request failing with 401. There is nothing to log in to yet, so an unreadable
session is not an error condition.

*Corrected 2026-08-25.* **The 90 days slide.** Both the signature timestamp and the browser's
`Max-Age` are absolute, so a cookie issued only at mint expired 90 days later however active its
owner had been — a daily visitor was silently handed a fresh guest and a fresh $10,000 on day 90,
their real row orphaned until the cleaner reaped it. The cookie is therefore re-issued on **every**
resolve, mint or not: every response from a caller-resolving route carries a `Set-Cookie` with the
same user id and a full 90 days. Re-issuing unconditionally rather than past some fraction of the
cookie's life is deliberate — there is no threshold to reason about, and the session always has its
full life left as of the last request. The TTL is there to expire *idle* guests
(`GUEST_TTL_DAYS`), and this is what keeps it from expiring active ones.

*Corrected 2026-08-25.* **Error responses carry the cookie too.** The 4xx/422/500 envelope of §1 is
built by an exception handler, which does not inherit the headers of the dependency that resolved
the caller. Those handlers re-attach the `Set-Cookie` explicitly; without it a cookie-less first
request that failed created a guest (a profile, ten watchlist rows and a snapshot) and told the
browser nothing about it, so the retry created another.

**Four routes never mint a guest and never touch the cookie:** `GET /api/health`,
`GET /api/stream/prices`, `GET`/`POST /api/admin/cleanup` (§8), and the SPA catch-all
`GET /{path}` that serves the static frontend. The first two are read-only against shared,
non-user-scoped state (process health; the shared price cache); the cleanup route is authorized by
a shared secret rather than by a user and deletes rows on a scheduler's behalf; the catch-all
serves files (a path that is a directory is served from the `index.html` inside it, which is how
an exported route such as `/privacy/` resolves — see PLAN.md §11). None of them needs — or
creates — a user. (Six more routes never *mint* a guest either, but do read or write the cookie
directly rather than never touching it at all — see §0.1's opening paragraph for that
distinction.)

---

## 0.1 Sign-in — OAuth routes

*Added 2026-08-25. Optional and additive: with no `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` or
`GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` configured, `GET /api/auth/providers` reports an empty
list, the frontend renders no sign-in control at all (`AccountMenu`), and everything above in §0
is unchanged. See `docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md` §5 for the
full design and §5.1 for the decision matrix these routes carry out.*

**Only `GET /api/auth/me` resolves — and, when there is none, mints — a caller.** It uses the same
`CurrentUserDep` as every other user-scoped route, so it re-issues the cookie on every response
exactly as §0 describes, and it is the call the frontend's session store makes on mount — which is
where a first-time visitor's guest account actually comes from, not the SPA catch-all. Every other
route below reads `trader_session` itself, when it needs to, and writes it at most once on the
response it returns; none of them carries `CurrentUserDep`. That is deliberate: a callback that
depended on it would emit two competing `Set-Cookie: trader_session` headers on the same response —
one for the guest that was there, one for the account the callback resolved to — and leave the
browser to pick one arbitrarily.

### `GET /api/auth/providers`

Does **not** resolve or mint a caller — this is the one read a page can make before anyone has a
session at all.

```json
{"providers": [{"name": "google", "label": "Google"}, {"name": "github", "label": "GitHub"}]}
```

Only providers with both halves of their credential pair configured appear, in this fixed order
(Google, then GitHub) regardless of which was configured first.

### `GET /api/auth/login/{provider}`

Redirects (302, via Authlib) the browser to the provider's own consent screen. A full-page
navigation, not a fetch — a JSON response here would put the provider's login page inside an XHR,
which is not renderable. `provider` not in `{google, github}`, or configured with no credentials on
this deployment, → `AUTH_PROVIDER_UNAVAILABLE` (404): the route genuinely does not exist here, which
lets the frontend simply not render a button for it rather than render one that dead-ends.

### `GET /api/auth/callback/{provider}`

Where the provider sends the browser back. Trades the code for a token, reduces the provider's
answer to a profile (`sub`/`id`, email, name, avatar), looks up whether that `(provider,
provider_user_id)` pair is already linked to an account, and carries out exactly one of four
outcomes:

| Outcome | When | Result |
|---|---|---|
| **Promote** | Identity is new; caller already holds a session | That row is attached to the identity and marked a signed-in user. Same id, so the portfolio carries over. |
| **Create** | Identity is new; caller holds no session | A fresh seeded account is created and the identity attached to it. |
| **Switch** | Identity is already linked; caller's current guest has no real activity to lose | The cookie moves to point at the account that owns the identity. The caller's previous guest row, if any, is left alone and expires on its own idle timer. |
| **Conflict** | Identity is already linked; caller is a guest with real activity (D-2) | Nothing is written yet. See below. |

Promote/Create/Switch all end the same way: `307` to `/`, with exactly one
`Set-Cookie: trader_session` naming the resulting account. Conflict responds `307` to
`/?claim=conflict&token=<token>` with **no** `Set-Cookie` at all — the guest keeps its session,
untouched, until it confirms via `POST /api/auth/claim`. `token` is short-lived, single-use, and
bound to the session that received it (`app/auth/claim.py`); the frontend's `ClaimConflictDialog`
reads it from the query string and shows: *"That account already has a portfolio. Signing in opens
the portfolio that already belongs to this account. Your current guest activity will be discarded
and cannot be recovered."*

Identities are matched by `(provider, provider_user_id)` **only, never by email** (D-6). This is
deliberate, not an oversight: a provider does not always guarantee its email address is verified,
and matching two different providers' identities because they happen to report the same address is
an account-takeover vector — anyone who can get that address accepted by either provider's signup
flow could walk into an account they do not own. The cost is that the same person signing in first
with Google and later with GitHub, using the same address, ends up with two accounts rather than
one merged account; that is the accepted trade-off, not a bug to be fixed with an email fallback.

Errors: a state/PKCE mismatch (a bookmarked callback URL, a back button, a sign-in begun before a
redeploy rotated the secret) → `AUTH_STATE_INVALID` (400), ordinary rather than sinister. Any other
failure trading the code or fetching the profile → `AUTH_EXCHANGE_FAILED` (502).

### `GET /api/auth/me`

```json
{
  "id": "3f2a1c9e-...",
  "kind": "guest",
  "email": null,
  "name": null,
  "avatar": null,
  "hasActivity": false
}
```

`kind` is `"guest"` or `"user"` — a user has at least one linked OAuth identity and never expires;
a guest expires after `GUEST_TTL_DAYS` idle. `hasActivity` is whether this guest has done anything
beyond the seeded starting state (a trade, a watchlist edit, a chat message) — it drives both the
"sign in to keep this portfolio" hint copy and, indirectly, whether a future sign-in on this
session could ever produce a claim conflict.

### `POST /api/auth/logout`

No request body. Response `200`: `{"ok": true}`. Clears the session cookie; it sets nothing new.
The next request to any caller-resolving route mints a fresh guest.

### `POST /api/auth/claim`

Request: `{"token": "<claim token from the callback redirect>"}`

Response `200`: `{"ok": true}` (matching `logout`), with `Set-Cookie: trader_session` naming the
account the token pointed at — the same one offered in the callback's redirect, never a different
one. A token that is expired, tampered with, already used, or not bound to the caller's current
session → `CLAIM_TOKEN_INVALID` (400). Refusal leaves the caller's cookie exactly where it was, so
nothing downstream is stale.

### `GET /api/auth/dev-login/{user_id}`

E2E only. Signs a session cookie for `user_id` with no provider involved at all — unauthenticated
session forgery, by design: anyone who can reach it becomes any user by guessing an id. Answers
`AUTH_PROVIDER_UNAVAILABLE` (404), not 403, when `AUTH_MOCK` is unset (the default and what every
non-test deployment should run with), so a deployment that has it switched off does not even
reveal that the route exists. **The same code and status also answer a `user_id` that does not
exist** ("No such user.") when `AUTH_MOCK=true` — the two 404s are indistinguishable on the wire,
so a bad id and a switched-off route look identical to a caller debugging one. On success: `307`
to `/` with the cookie set. `AUTH_MOCK=true` is what `test/docker-compose.test.yml` sets for the
E2E suite; it is never set in `docker-compose.yml` or on Vercel.

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
| `WATCHLIST_FULL` | 400 | *This caller's own* watchlist already holds 25 tickers (`watchlist_cap`) |
| `TICKER_NOT_FOUND` | 404 | Ticker is not on the watchlist / has no history |
| `PRICE_UNAVAILABLE` | 409 | No cached price yet; the trade is refused rather than filled at 0 |
| `VALIDATION_ERROR` | 422 | Request body failed schema validation |
| `VALUATION_UNAVAILABLE` | 500 | A held position has no cached price, so the portfolio cannot be valued |
| `MARKET_CAPACITY_FULL` | 503 | The *global* tracked-ticker set (across every user, `market_capacity`, default 100) is full. Distinct from `WATCHLIST_FULL`: this can fire for a caller whose own watchlist holds three tickers, because the deployment as a whole is already tracking its cap. |
| `CLEANUP_FORBIDDEN` | 403 | `POST`/`GET /api/admin/cleanup` called without a valid secret in either `X-Cleanup-Secret` or `Authorization: Bearer`, or no secret is configured at all |
| `AUTH_PROVIDER_UNAVAILABLE` | 404 | `{provider}` in `/api/auth/login/{provider}` or `/api/auth/callback/{provider}` is not `google`/`github`, or this deployment has no credentials for it; also what `/api/auth/dev-login/{user_id}` answers when `AUTH_MOCK` is unset |
| `AUTH_STATE_INVALID` | 400 | The OAuth callback's state or PKCE verifier did not match — a bookmarked callback URL, a back button, or a secret rotated mid-flow, not an outage |
| `AUTH_EXCHANGE_FAILED` | 502 | The provider refused the code exchange or the userinfo/profile request |
| `CLAIM_TOKEN_INVALID` | 400 | `POST /api/auth/claim`'s token is expired, tampered with, already used, or not bound to the caller's current session |
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
- Never mints a session cookie (§0) — the stream serves the one shared price cache, not a per-user
  view, so there is no caller to resolve.

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
  rather than filling at 0. If the *global* tracked-ticker set is already at capacity, the trade
  fails with `MARKET_CAPACITY_FULL` instead — a limit on the deployment, not on this caller.
- Validation order and error codes: `INVALID_TICKER` → `INVALID_QUANTITY` → `PRICE_UNAVAILABLE` →
  `INSUFFICIENT_CASH` / `INSUFFICIENT_SHARES`.

### `GET /api/portfolio/history?limit=500`

`limit` defaults to 500, capped at 5000. Ordered oldest-first for direct charting.

```json
{"snapshots": [{"total_value": 10000.00, "recorded_at": "2026-08-18T09:00:00Z"}]}
```

A snapshot is written: once at t=0, the moment a guest is minted or reset (so a brand-new
portfolio's chart is never empty); immediately after every trade; and — for every user active
within the last hour — every 30 seconds by a background task (the container target) or on the next
`GET /api/portfolio` past the interval (the serverless target, which has no background task; see
`planning/VERCEL_DEPLOYMENT.md`). Rows older than 7 days are pruned, per user.

---

## 4. Watchlist

### `GET /api/watchlist`

```json
{"tickers": ["AAPL", "GOOGL", "MSFT"], "cap": 25}
```

This is the **calling user's own** watchlist, scoped by the session cookie (§0) — every user has an
independent list, capped independently at `cap`. Ordered by `added_at` ascending — the frontend
renders in exactly this order and never derives row order from the SSE map. **No prices are
returned**; prices come from SSE only (DECISIONS D-24).

### `POST /api/watchlist`

Request `{"ticker": "pypl"}` — canonicalized server-side. Idempotent: adding an existing ticker
returns 200 and changes nothing.

Response `200`: `{"tickers": ["AAPL", "...", "PYPL"], "cap": 25}`

Errors: `INVALID_TICKER`, `WATCHLIST_FULL` (this caller's own list is at cap), `MARKET_CAPACITY_FULL`
(the global tracked set is at cap, even though this caller's list has room).

### `DELETE /api/watchlist/{ticker}`

Response `200`: `{"tickers": [...], "cap": 25}`. Errors: `INVALID_TICKER`, `TICKER_NOT_FOUND`.

Removing a ticker you still hold is **allowed**. The watchlist row is deleted but the price feed
continues, because the price source tracks `union(watchlist, tickers with an open position)`
**across every user, not just the caller** (DECISIONS D-01/D-02/D-03 — superseded to be global; see
`planning/DECISIONS.md`). Even after this caller drops both their watchlist entry and their
position, the ticker stays tracked as long as any other user still watches or holds it. The
position remains visible in the positions table and heatmap.

---

## 5. Price history — `GET /api/history/{ticker}`

Seeds charts on first paint so they are not empty after a reload.

```json
{
  "ticker": "AAPL",
  "points": [{"timestamp": 1755500000.123, "price": 190.02}]
}
```

Up to the last 600 ticks, oldest-first, held in memory only — the buffer is empty after a restart.
It is per-ticker and shared by every user, so `POST /api/reset` deliberately leaves it alone:
clearing it on one person's reset would blank everyone else's main chart too. `timestamp` is Unix
float seconds, matching the SSE payload. A ticker that has never been tracked returns
`TICKER_NOT_FOUND`; a tracked ticker with no ticks yet returns an empty `points` array.

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

`status` is `"ok"` or `"degraded"`. `market_source` is `"simulator"`, `"massive"`, or
`"deterministic"` (a serverless deployment with no background task to tick a stateful simulator).
`seconds_since_last_tick` is `null` before the first tick. E2E waits on this instead of sleeping.
Never mints a session cookie (§0) — it reports on shared process state, not on any one caller.

### `POST /api/reset`

Restores the **calling user's own** seeded state: $10,000 cash, the ten default tickers, no
positions, no trades, no chat history, one fresh snapshot. It never touches any other user's rows —
notably, it does **not** clear the price history ring buffer, which is per-ticker and shared by
every user; wiping it on one person's reset would blank everyone else's main chart. Returns the
same body as `GET /api/portfolio`.

### `GET` / `POST /api/admin/cleanup`

Deletes guest accounts idle past `GUEST_TTL_DAYS`; the foreign keys cascade away their watchlist,
positions, trades, chat, and snapshots with them. Never expires a signed-in user (there are none
yet). Guarded by a shared secret rather than by the caller's identity — there is no admin user in
this app, and the route must be callable by a scheduler with no cookie of its own:

- Requires the secret in one of two headers, compared with a constant-time check against the same
  configured value (`Settings.cleanup_secret`, itself resolved from `CLEANUP_SECRET` falling back
  to `CRON_SECRET`): `X-Cleanup-Secret: <secret>`, or `Authorization: Bearer <secret>` — the header
  Vercel Cron auto-attaches when `CRON_SECRET` is set, since a `vercel.json` `crons` entry cannot
  be configured to send a custom header at all. Missing or wrong on both → `CLEANUP_FORBIDDEN`
  (403). No secret configured on either variable rejects every call.
- Both methods run the same logic. `GET` exists because Vercel Cron issues a GET; `POST` is for
  manual/curl use.
- Response `200`: `{"deleted": 3}` — the count of guests removed.
- This route is one of the four that never mint a guest (§0); calling it does not create a session.
- A header value carrying a byte ≥ `0x80` is rejected as a wrong secret (403), not answered with a
  500: the comparison is made on the UTF-8 bytes, because Starlette decodes header bytes as latin-1
  and `secrets.compare_digest` refuses a `str` with a codepoint above 127.

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
