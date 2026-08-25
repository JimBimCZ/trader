# Per-User Scoping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every row in the database belong to a real user, minted from a signed cookie, so the app is fully multi-user with no way to sign in yet.

**Architecture:** A stateless signed cookie carries a user id. A `current_user` FastAPI dependency resolves it — loading the row, or minting and seeding a guest when there is no valid cookie — and per-request factories in `deps.py` build user-scoped repositories and services over the shared connection pool. `DEFAULT_USER_ID` and every `user_id` parameter default are deleted, so a repository constructed without a user raises a `TypeError` at construction rather than silently reading someone else's rows. The three subsystems that are legitimately global — the ticker reconciler, the snapshot writer, and guest cleanup — become explicitly global instead of accidentally single-user.

**Tech Stack:** FastAPI, asyncpg, Postgres 16 / Neon, `itsdangerous` for cookie signing, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md` — this plan implements **§6 and §7**, plus the `kind` / `last_seen_at` half of §4 and the session cookie of §3. It is **phase 2 of 3** in that spec's §13.

## Global Constraints

- **`DEFAULT_USER_ID` must not exist anywhere in `backend/app/` when this plan is done.** Its deletion is the mechanism behind spec decision D-5; a grep for it is part of the final task's verification.
- **No `user_id` parameter anywhere may carry a default value.** Construction without a user must fail loudly, not fall back.
- Cookie name is `trader_session`; payload is `{"uid": <id>}` signed with `SESSION_SECRET` via `itsdangerous`. `kind` is deliberately **not** in the cookie — the row is the only source of truth.
- Cookie flags: `HttpOnly`, `SameSite=Lax`, `Secure` when not on localhost, `Max-Age` 90 days (`7776000` seconds).
- `GET /api/health` and `GET /api/stream/prices` are **exempt** from user resolution — they must never mint a guest.
- `last_seen_at` writes are throttled to ~5 minutes; an unthrottled write turns every GET into a Neon round trip.
- Per-user watchlist cap stays **25**, reported as `WATCHLIST_FULL`. The new global tracked cap is **100**, reported as `MARKET_CAPACITY_FULL` (503). Never report the global limit as `WATCHLIST_FULL`.
- `GUEST_TTL_DAYS` defaults to `7`.
- Migrations are append-only and idempotent, with no version table. Never edit a deployed statement; add a new one.
- Timestamps are ISO-8601 UTC strings, written via `app/clock.py`'s `utcnow_iso()`, matching every existing table.
- Out of scope for this phase: OAuth routes, `oauth_identities`, the `email` / `display_name` / `avatar_url` columns, and all frontend work. Those are phase 3.

---

## File Structure

**New files:**

| File | Responsibility |
|---|---|
| `backend/app/identity/__init__.py` | Package exports: `SessionCookie`, `UserStore`, `User` |
| `backend/app/identity/cookie.py` | Sign, verify, and reject tampered session cookies. Knows nothing about the database. |
| `backend/app/identity/store.py` | `UserStore` — load a user row, mint and seed a guest, touch `last_seen_at`, list recently-seen users, delete expired guests. The only module that writes `users_profile.kind`. |
| `backend/app/identity/models.py` | The `User` dataclass |
| `backend/app/system/cleanup.py` | `GuestCleaner` — the daily background task, and the function the admin route calls |
| `backend/tests/identity/test_cookie.py` | Signing, verification, tamper rejection |
| `backend/tests/identity/test_store.py` | Guest minting, seeding, `last_seen_at` throttling |
| `backend/tests/test_cross_user_isolation.py` | **The highest-value tests in the suite** — user A can neither read nor mutate user B's rows |
| `backend/tests/test_guest_cleanup.py` | Expiry and its cascades |

**Modified files:**

| File | Change |
|---|---|
| `backend/app/db/connection.py` | Delete `DEFAULT_USER_ID` |
| `backend/app/db/schema.py` | `users_profile` gains `kind` and `last_seen_at` for fresh databases |
| `backend/app/db/migrations.py` | Migration 002 adds those columns and the index to existing databases |
| `backend/app/db/seed.py` | `seed_if_empty(db, settings)` becomes `seed_user(db, settings, user_id)` — seeds one user, not "the" user |
| `backend/app/config.py` | `session_secret`, `guest_ttl_days`, `cleanup_secret`, `market_capacity` |
| `backend/app/deps.py` | Per-request `current_user` and the service factories — the heart of this phase |
| `backend/app/main.py` | Lifespan keeps only shared state; service construction moves out |
| `backend/app/errors.py` | `MarketCapacityFullError` |
| `backend/app/reconcile.py` | Both sides go global |
| `backend/app/portfolio/repository.py` | Delete the four `user_id` defaults |
| `backend/app/watchlist/repository.py` | Delete the `user_id` default |
| `backend/app/llm/repository.py` | Delete the `user_id` default |
| `backend/app/portfolio/snapshot_writer.py` | Iterate recently-seen users |
| `backend/app/portfolio/service.py` | Snapshot-on-read for the serverless path |
| `backend/app/portfolio/router.py` | Snapshot-on-read hook |
| `backend/app/system/service.py` | `ResetService` scoped to the caller |
| `backend/app/system/router.py` | Admin cleanup route |
| `backend/app/market/stream.py` | Delete the heartbeat plumbing |
| `backend/tests/conftest.py` | `seeded_db` runs migrations; new per-user fixtures |
| `backend/tests/conftest_services.py` | Build services for an explicit user |
| `vercel.json` | Cron entry for the cleanup endpoint |
| `.env.example` | The new variables |

**Dependency:** `itsdangerous>=2.2.0` is added to `backend/pyproject.toml`. It arrives transitively with Starlette today, but this plan uses it directly, so it must be declared.

---

### Task 1: Test fixtures see the production schema

The `db` and `seeded_db` fixtures call `init_db` and `seed_if_empty` but never `run_migrations`, so almost every repository and service test runs against tables with **no foreign keys** — a shape production does not have. This was deferred from phase 1 specifically to land here, because every later task in this plan depends on foreign keys actually being present in tests.

**Files:**
- Modify: `backend/tests/conftest.py` (the `seeded_db` fixture)
- Test: `backend/tests/db/test_fixture_shape.py` (create)

**Interfaces:**
- Consumes: `run_migrations(db)` from `app.db.migrations`
- Produces: a `seeded_db` fixture whose tables carry the five `fk_<table>_user` foreign keys

- [ ] **Step 1: Write the failing test**

Create `backend/tests/db/test_fixture_shape.py`:

```python
"""The fixtures must hand tests the schema production actually runs.

Without this, a write that violates a foreign key passes the whole suite and
500s in production -- the tests would be asserting against a shape that
exists nowhere else.
"""

from __future__ import annotations

import pytest

EXPECTED_FKS = {
    "fk_watchlist_user",
    "fk_positions_user",
    "fk_trades_user",
    "fk_portfolio_snapshots_user",
    "fk_chat_messages_user",
}


class TestSeededDbIsMigrated:
    async def test_every_per_user_table_has_its_foreign_key(self, seeded_db):
        rows = await seeded_db.fetch_all(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE c.contype = 'f' AND n.nspname = current_schema()"
        )
        assert {row["conname"] for row in rows} == EXPECTED_FKS

    async def test_the_foreign_key_is_actually_enforced(self, seeded_db):
        """A constraint that exists but is NOT VALID would pass the check above."""
        import asyncpg

        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await seeded_db.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) "
                "VALUES (?, ?, ?, ?)",
                ("probe-row", "no-such-user", "AAPL", "2026-01-01T00:00:00Z"),
            )
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/db/test_fixture_shape.py -v
```

Expected: both tests FAIL — the first with an empty set, the second because the insert succeeds where it should raise.

- [ ] **Step 3: Make `seeded_db` run migrations**

In `backend/tests/conftest.py`, replace the `seeded_db` fixture:

```python
@pytest_asyncio.fixture
async def seeded_db(db: Database, settings: Settings):
    """An initialized, seeded, migrated database -- production's exact shape.

    Migrations run after seeding, matching main.py's lifespan order: migration
    001 adds foreign keys to users_profile, so every per-user row must already
    point at a profile that exists. The bare `db` fixture deliberately stays
    unmigrated; it models "schema only" for the db-layer tests that assert on
    what initialize_schema alone produces.
    """
    await seed_if_empty(db, settings)
    await run_migrations(db)
    return db
```

Add the import at the top of the file, beside the existing `app.db` import:

```python
from app.db import Database, init_db, run_migrations, seed_if_empty
```

- [ ] **Step 4: Run the new test, then the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/db/test_fixture_shape.py -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: the new tests PASS and the full suite stays green. If any existing test now fails on a foreign key, that test was relying on the un-migrated shape — **report it rather than reverting this change**; it is exactly the class of bug this task exists to expose.

- [ ] **Step 5: Verify formatting and lint (CI runs both)**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
```

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/db/test_fixture_shape.py
git commit -m "Give the seeded test fixture production's foreign keys"
```

---

### Task 2: Schema and migration for `kind` and `last_seen_at`

`users_profile` needs to distinguish a guest from a signed-in user and record when a session was last active. `CREATE TABLE IF NOT EXISTS` cannot add a column to a table Neon already has, so this needs both: the column in `schema.py` for fresh databases, and a migration for existing ones.

Only `kind` and `last_seen_at` land here. `email`, `display_name`, `avatar_url` and the `oauth_identities` table have no reader until phase 3 and are deliberately left out.

**Files:**
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Test: `backend/tests/db/test_migrations.py` (extend)

**Interfaces:**
- Produces: `users_profile.kind TEXT NOT NULL DEFAULT 'guest' CHECK (kind IN ('guest','user'))` and `users_profile.last_seen_at TEXT NOT NULL`, plus index `idx_users_kind_seen`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/db/test_migrations.py`:

```python
class TestMigration002AddsIdentityColumns:
    async def test_kind_and_last_seen_at_exist_after_migrating(self, db):
        await run_migrations(db)

        rows = await db.fetch_all(
            "SELECT column_name, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = 'users_profile' AND table_schema = current_schema()"
        )
        columns = {row["column_name"]: row for row in rows}

        assert "kind" in columns
        assert columns["kind"]["is_nullable"] == "NO"
        assert "guest" in (columns["kind"]["column_default"] or "")
        assert "last_seen_at" in columns
        assert columns["last_seen_at"]["is_nullable"] == "NO"

    async def test_kind_rejects_a_value_outside_the_check(self, db):
        await run_migrations(db)
        await db.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at, last_seen_at) "
            "VALUES (?, ?, ?, ?)",
            ("check-probe", 10000.0, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

        import asyncpg

        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await db.execute(
                "UPDATE users_profile SET kind = 'admin' WHERE id = ?", ("check-probe",)
            )

    async def test_the_kind_seen_index_exists(self, db):
        await run_migrations(db)
        rows = await db.fetch_all(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'users_profile' AND schemaname = current_schema()"
        )
        assert "idx_users_kind_seen" in {row["indexname"] for row in rows}
```

Confirm `import pytest` is already at the top of that file; add it if not.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/db/test_migrations.py -k Migration002 -v
```

Expected: FAIL — `assert "kind" in columns` fails, the column does not exist.

- [ ] **Step 3: Add the columns to `schema.py` for fresh databases**

In `backend/app/db/schema.py`, replace the `users_profile` block:

```sql
CREATE TABLE IF NOT EXISTS users_profile (
    id           TEXT PRIMARY KEY,
    cash_balance DOUBLE PRECISION NOT NULL,
    created_at   TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'guest' CHECK (kind IN ('guest','user')),
    last_seen_at TEXT NOT NULL DEFAULT ''
);
```

`last_seen_at` carries a `DEFAULT ''` purely so the `NOT NULL` can be added to a table that already has rows; every writer sets it explicitly.

- [ ] **Step 4: Add migration 002 for existing databases**

In `backend/app/db/migrations.py`, append to `MIGRATIONS` — **below** the existing 001 entries, never edited into them:

```python
    # 002 -- identity columns. ADD COLUMN IF NOT EXISTS is idempotent, and the
    # CHECK is attached in the same statement so a column can never exist
    # without it. Neon already has users_profile from phase 1, so CREATE TABLE
    # IF NOT EXISTS in schema.py cannot deliver these -- this is the gap that
    # bites on the second deploy rather than the first.
    "ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL "
    "DEFAULT 'guest' CHECK (kind IN ('guest','user'))",
    "ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS last_seen_at TEXT NOT NULL DEFAULT ''",
    # Backfills the empty default for rows that predate the column, so
    # last_seen_at is a real timestamp everywhere before anything reads it.
    "UPDATE users_profile SET last_seen_at = created_at WHERE last_seen_at = ''",
    "CREATE INDEX IF NOT EXISTS idx_users_kind_seen ON users_profile (kind, last_seen_at)",
```

- [ ] **Step 5: Run the new tests, the idempotency test, and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/db/ -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: PASS. `test_migrations.py` already asserts that running the list twice changes nothing — that test must still pass, which is what proves 002 is idempotent.

- [ ] **Step 6: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/app/db/schema.py backend/app/db/migrations.py backend/tests/db/test_migrations.py
git commit -m "Add kind and last_seen_at to users_profile"
```

---

### Task 3: The signed session cookie

A stateless signed cookie carrying one user id. No session table, so no read on every request. This module knows nothing about the database — it is pure signing and verification, which is what makes it cheap to test exhaustively.

**Files:**
- Create: `backend/app/identity/__init__.py`, `backend/app/identity/cookie.py`
- Modify: `backend/app/config.py`, `backend/pyproject.toml`, `.env.example`
- Test: `backend/tests/identity/__init__.py`, `backend/tests/identity/test_cookie.py` (create both)

**Interfaces:**
- Produces:
  - `SessionCookie(secret: str)` with `.sign(user_id: str) -> str` and `.verify(raw: str | None) -> str | None`
  - `COOKIE_NAME = "trader_session"`, `COOKIE_MAX_AGE = 7776000`
  - `Settings.session_secret: str`

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    "itsdangerous>=2.2.0",
```

Then:

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv lock
```

This needs `dangerouslyDisableSandbox: true` — `uv lock` reaches the network.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/identity/__init__.py` (empty) and `backend/tests/identity/test_cookie.py`:

```python
"""The session cookie is the only thing standing between two users' data.

There is no session table to check against, so a forged or tampered cookie
that verified would hand out someone else's portfolio. These tests are the
whole defence.
"""

from __future__ import annotations

import pytest

from app.identity.cookie import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie

SECRET = "test-secret-not-used-anywhere-real"


class TestRoundTrip:
    def test_a_signed_id_verifies_back_to_itself(self):
        cookie = SessionCookie(SECRET)
        assert cookie.verify(cookie.sign("user-abc")) == "user-abc"

    def test_the_signed_value_is_not_the_bare_id(self):
        """A cookie that were just the id would let anyone name any user."""
        cookie = SessionCookie(SECRET)
        assert cookie.sign("user-abc") != "user-abc"


class TestRejection:
    @pytest.mark.parametrize(
        "bad",
        [
            None,
            "",
            "user-abc",
            "garbage",
            "eyJ1aWQiOiAidXNlci1hYmMifQ",  # unsigned base64 of the payload
        ],
    )
    def test_anything_unsigned_is_refused(self, bad):
        assert SessionCookie(SECRET).verify(bad) is None

    def test_a_tampered_payload_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie.sign("user-abc")
        tampered = ("X" if signed[0] != "X" else "Y") + signed[1:]
        assert cookie.verify(tampered) is None

    def test_a_cookie_signed_with_another_secret_is_refused(self):
        """Rotating SESSION_SECRET must invalidate every existing session."""
        signed = SessionCookie("old-secret").sign("user-abc")
        assert SessionCookie(SECRET).verify(signed) is None

    def test_an_expired_cookie_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie.sign("user-abc")
        assert cookie.verify(signed, max_age=-1) is None


class TestContract:
    def test_the_name_and_lifetime_match_the_spec(self):
        assert COOKIE_NAME == "trader_session"
        assert COOKIE_MAX_AGE == 7776000  # 90 days
```

- [ ] **Step 3: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/identity/test_cookie.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.identity'`.

- [ ] **Step 4: Write the implementation**

Create `backend/app/identity/cookie.py`:

```python
"""Signing and verifying the session cookie.

Deliberately knows nothing about the database. The cookie carries the user id
and nothing else -- notably not `kind`, because signing in promotes a guest
row in place and a copy of `kind` in the cookie would then be stale. The row
is the only source of truth.
"""

from __future__ import annotations

import logging

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

#: Cookie name, per the spec's session contract.
COOKIE_NAME = "trader_session"

#: 90 days, in seconds.
COOKIE_MAX_AGE = 7776000

_SALT = "trader-session-v1"


class SessionCookie:
    """Signs a user id into a cookie value and reads it back."""

    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)

    def sign(self, user_id: str) -> str:
        return self._serializer.dumps({"uid": user_id})

    def verify(self, raw: str | None, max_age: int = COOKIE_MAX_AGE) -> str | None:
        """Return the user id, or None for anything not validly signed.

        Every rejection returns None rather than raising: an unreadable cookie
        is not an error condition, it is a request that gets a fresh guest.
        """
        if not raw:
            return None
        try:
            payload = self._serializer.loads(raw, max_age=max_age)
        except SignatureExpired:
            return None
        except BadSignature:
            # Worth a log line: in volume this is either a secret rotation or
            # someone probing.
            logger.warning("Rejected a session cookie with a bad signature")
            return None
        if not isinstance(payload, dict):
            return None
        uid = payload.get("uid")
        return uid if isinstance(uid, str) and uid else None
```

Create `backend/app/identity/__init__.py`:

```python
"""User identity: the session cookie and the user store."""

from .cookie import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie

__all__ = ["COOKIE_MAX_AGE", "COOKIE_NAME", "SessionCookie"]
```

- [ ] **Step 5: Add `session_secret` to config**

In `backend/app/config.py`, add the field to `Settings` beside `watchlist_cap`:

```python
    session_secret: str = ""
```

And in the `from_env` classmethod (follow the file's existing pattern for reading a variable), resolve it:

```python
        # A generated secret is correct for local dev and catastrophic in
        # production: it changes on every restart, which signs out every user
        # and permanently orphans every guest portfolio, since the cookie is
        # the only pointer to the row.
        session_secret = os.environ.get("SESSION_SECRET", "").strip()
        if not session_secret:
            session_secret = secrets.token_urlsafe(32)
            logger.warning(
                "SESSION_SECRET is not set; generated an ephemeral one. Every "
                "restart will sign out all users and orphan every guest "
                "portfolio. Set it before deploying."
            )
```

Add `import secrets` to the file's imports, and confirm a module-level `logger` exists — if not, add `logger = logging.getLogger(__name__)` and `import logging`.

- [ ] **Step 6: Document the variable**

In `.env.example`, add:

```bash
# Required in production: signs the session cookie that identifies a user.
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
# Left unset, an ephemeral one is generated at startup -- every restart then
# signs out every user and permanently orphans every guest portfolio.
SESSION_SECRET=
```

- [ ] **Step 7: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/identity/ -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: all PASS.

- [ ] **Step 8: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/app/identity backend/app/config.py backend/pyproject.toml backend/uv.lock \
        backend/tests/identity .env.example
git commit -m "Add the signed session cookie"
```

---

### Task 4: The user store — minting, loading, and touching guests

The database side of identity. `seed_if_empty` becomes `seed_user`: today it asks "is the database empty?", which is the single-user question. The multi-user question is "does *this* user have rows?", and the answer is always no at the moment a guest is minted.

**Files:**
- Create: `backend/app/identity/models.py`, `backend/app/identity/store.py`
- Modify: `backend/app/db/seed.py`, `backend/app/db/__init__.py`, `backend/app/identity/__init__.py`, `backend/app/config.py`
- Test: `backend/tests/identity/test_store.py` (create)

**Interfaces:**
- Consumes: `Database` from `app.db`, `utcnow_iso()` from `app.clock`
- Produces:
  - `User(id: str, cash_balance: float, kind: str, created_at: str, last_seen_at: str)` — a frozen dataclass
  - `UserStore(db: Database, settings: Settings)` with:
    - `async get(user_id: str) -> User | None`
    - `async mint_guest() -> User` — inserts, seeds, returns
    - `async touch(user: User) -> None` — throttled `last_seen_at` write
    - `async list_active_since(iso_cutoff: str) -> list[str]`
    - `async delete_expired_guests(iso_cutoff: str) -> int`
  - `seed_user(db: Database, settings: Settings, user_id: str) -> None` in `app.db.seed`
  - `Settings.guest_ttl_days: int = 7`, `Settings.last_seen_throttle_seconds: float = 300.0`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/identity/test_store.py`:

```python
"""Guest minting, seeding, and the last_seen_at throttle."""

from __future__ import annotations

from app.identity.store import UserStore


class TestMinting:
    async def test_a_minted_guest_starts_with_cash_and_the_default_watchlist(
        self, db, settings
    ):
        store = UserStore(db, settings)

        user = await store.mint_guest()

        assert user.kind == "guest"
        assert user.cash_balance == settings.initial_cash
        rows = await db.fetch_all(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (user.id,)
        )
        assert len(rows) == 10

    async def test_two_guests_get_separate_rows_and_separate_watchlists(
        self, db, settings
    ):
        store = UserStore(db, settings)

        first = await store.mint_guest()
        second = await store.mint_guest()

        assert first.id != second.id
        for user in (first, second):
            rows = await db.fetch_all(
                "SELECT ticker FROM watchlist WHERE user_id = ?", (user.id,)
            )
            assert len(rows) == 10

    async def test_a_minted_guest_can_be_loaded_back(self, db, settings):
        store = UserStore(db, settings)
        minted = await store.mint_guest()

        loaded = await store.get(minted.id)

        assert loaded is not None
        assert loaded.id == minted.id
        assert loaded.kind == "guest"

    async def test_an_unknown_id_loads_as_none(self, db, settings):
        """A cookie signed before a database reset points at a row that is
        gone; that must mint a fresh guest, not raise."""
        assert await UserStore(db, settings).get("no-such-user") is None


class TestTouchThrottle:
    async def test_the_first_touch_after_the_window_writes(self, db, settings):
        store = UserStore(db, settings)
        user = await store.mint_guest()
        await db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user.id),
        )
        stale = await store.get(user.id)

        await store.touch(stale)

        refreshed = await store.get(user.id)
        assert refreshed.last_seen_at != "2020-01-01T00:00:00+00:00"

    async def test_a_touch_inside_the_window_does_not_write(self, db, settings):
        """Unthrottled, every GET becomes a write -- a Neon round trip per
        read on the hottest path in the app."""
        store = UserStore(db, settings)
        user = await store.mint_guest()
        before = (await store.get(user.id)).last_seen_at

        await store.touch(await store.get(user.id))

        assert (await store.get(user.id)).last_seen_at == before


class TestExpiry:
    async def test_only_guests_past_the_cutoff_are_deleted(self, db, settings):
        store = UserStore(db, settings)
        old = await store.mint_guest()
        fresh = await store.mint_guest()
        await db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", old.id),
        )

        deleted = await store.delete_expired_guests("2021-01-01T00:00:00+00:00")

        assert deleted == 1
        assert await store.get(old.id) is None
        assert await store.get(fresh.id) is not None

    async def test_a_signed_in_user_never_expires(self, db, settings):
        store = UserStore(db, settings)
        user = await store.mint_guest()
        await db.execute(
            "UPDATE users_profile SET kind = 'user', last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user.id),
        )

        deleted = await store.delete_expired_guests("2021-01-01T00:00:00+00:00")

        assert deleted == 0
        assert await store.get(user.id) is not None

    async def test_deleting_a_guest_cascades_to_its_rows(self, db, settings):
        """The foreign keys are what make expiry one DELETE instead of six."""
        store = UserStore(db, settings)
        user = await store.mint_guest()
        await db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", user.id),
        )

        await store.delete_expired_guests("2021-01-01T00:00:00+00:00")

        rows = await db.fetch_all(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (user.id,)
        )
        assert rows == []


class TestActiveUsers:
    async def test_only_users_seen_since_the_cutoff_are_listed(self, db, settings):
        store = UserStore(db, settings)
        recent = await store.mint_guest()
        old = await store.mint_guest()
        await db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", old.id),
        )

        active = await store.list_active_since("2021-01-01T00:00:00+00:00")

        assert recent.id in active
        assert old.id not in active
```

**Use `seeded_db` throughout, not `db`.** Replace every `(self, db, settings)` signature above with `(self, seeded_db, settings)`, and every `db.` call with `seeded_db.`. The cascade test needs the foreign keys, which only the migrated fixture has (Task 1).

`seeded_db` also contains the transitional `default` user. It does not interfere: every assertion here is scoped by `user_id`, and `default` is a recently-seen guest, so it is neither expired nor missing from the active list. Do not delete it.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/identity/test_store.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.identity.store'`.

- [ ] **Step 3: Generalize the seeder**

Replace `seed_if_empty` in `backend/app/db/seed.py` with:

```python
async def seed_user(db: Database, settings: Settings, user_id: str) -> None:
    """Give one user their starting cash balance and the default watchlist.

    The profile row must already exist -- the watchlist rows carry a foreign
    key to it. Callers create the row and seed inside one transaction.

    This replaces seed_if_empty, whose "is the database empty?" question was
    the single-user form of "does this user have rows?". With many users the
    database is never empty after the first guest, so that check would have
    silently skipped seeding for everyone after the first.
    """
    now = utcnow_iso()
    for ticker in DEFAULT_WATCHLIST:
        await db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id, ticker) DO NOTHING",
            (str(uuid.uuid4()), user_id, canonicalize_ticker(ticker), now),
        )
    logger.info("Seeded %d watchlist tickers for %s", len(DEFAULT_WATCHLIST), user_id)
```

Keep `seed_if_empty` as a thin wrapper, so `main.py` and `ResetService` keep working unchanged until Task 6 switches them:

```python
async def seed_if_empty(db: Database, settings: Settings) -> bool:
    """Seed the shared `default` user if it does not exist yet.

    Transitional: kept only so the lifespan and ResetService keep working
    while per-request scoping is built. Task 6 deletes it along with
    DEFAULT_USER_ID.
    """
    existing = await db.fetch_one(
        "SELECT id FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    if existing is not None:
        return False
    now = utcnow_iso()
    async with db.transaction():
        await db.execute(
            "INSERT INTO users_profile "
            "(id, cash_balance, created_at, kind, last_seen_at) "
            "VALUES (?, ?, ?, 'guest', ?)",
            (DEFAULT_USER_ID, settings.initial_cash, now, now),
        )
        await seed_user(db, settings, DEFAULT_USER_ID)
    return True
```

Update `backend/app/db/__init__.py` to export **both** `seed_user` and `seed_if_empty`. Nothing else changes in this task — `main.py` and `ResetService` are untouched, so the suite stays green.

- [ ] **Step 4: Write the store**

Create `backend/app/identity/models.py`:

```python
"""The user record, as the rest of the app sees it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """One row of users_profile.

    `kind` distinguishes a guest from a signed-in user. It is read from the
    row on every request rather than carried in the cookie, so promoting a
    guest in place takes effect immediately.
    """

    id: str
    cash_balance: float
    kind: str
    created_at: str
    last_seen_at: str
```

Create `backend/app/identity/store.py`:

```python
"""Reading and writing users_profile.

The only module that writes `kind`. Everything else treats a user as opaque.
"""

from __future__ import annotations

import logging
import uuid

from ..clock import utcnow_iso
from ..config import Settings
from ..db import Database, seed_user
from .models import User

logger = logging.getLogger(__name__)


def _to_user(row) -> User:
    return User(
        id=row["id"],
        cash_balance=row["cash_balance"],
        kind=row["kind"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )


class UserStore:
    """Loads, mints, and expires users."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def get(self, user_id: str) -> User | None:
        row = await self._db.fetch_one(
            "SELECT id, cash_balance, kind, created_at, last_seen_at "
            "FROM users_profile WHERE id = ?",
            (user_id,),
        )
        return _to_user(row) if row is not None else None

    async def mint_guest(self) -> User:
        """Create a guest and seed it, atomically.

        One transaction: a profile row without its watchlist would be a user
        staring at an empty app, and the watchlist rows carry a foreign key to
        the profile, so the order inside is fixed.
        """
        user_id = f"guest_{uuid.uuid4().hex}"
        now = utcnow_iso()
        async with self._db.transaction():
            await self._db.execute(
                "INSERT INTO users_profile "
                "(id, cash_balance, created_at, kind, last_seen_at) "
                "VALUES (?, ?, ?, 'guest', ?)",
                (user_id, self._settings.initial_cash, now, now),
            )
            await seed_user(self._db, self._settings, user_id)
        logger.info("Minted guest %s", user_id)
        return User(
            id=user_id,
            cash_balance=self._settings.initial_cash,
            kind="guest",
            created_at=now,
            last_seen_at=now,
        )

    async def touch(self, user: User) -> None:
        """Refresh last_seen_at, at most once per throttle window.

        Written on every request this turns each GET into a write, which on
        Neon is a network round trip per read.
        """
        now = utcnow_iso()
        if _seconds_between(user.last_seen_at, now) < self._settings.last_seen_throttle_seconds:
            return
        await self._db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?", (now, user.id)
        )

    async def list_active_since(self, iso_cutoff: str) -> list[str]:
        rows = await self._db.fetch_all(
            "SELECT id FROM users_profile WHERE last_seen_at >= ?", (iso_cutoff,)
        )
        return [row["id"] for row in rows]

    async def delete_expired_guests(self, iso_cutoff: str) -> int:
        """Delete idle guests. The foreign keys cascade the rest away.

        Only guests: a signed-in user never expires.
        """
        rows = await self._db.fetch_all(
            "DELETE FROM users_profile "
            "WHERE kind = 'guest' AND last_seen_at < ? RETURNING id",
            (iso_cutoff,),
        )
        if rows:
            logger.info("Deleted %d expired guests", len(rows))
        return len(rows)
```

Add the helper at the bottom of `store.py`:

```python
def _seconds_between(earlier_iso: str, later_iso: str) -> float:
    """Elapsed seconds, treating an unparseable timestamp as 'long ago'.

    A row written before last_seen_at existed carries the backfilled
    created_at; anything genuinely unreadable should cause a write, not a
    crash on the hottest path in the app.
    """
    from datetime import datetime

    try:
        earlier = datetime.fromisoformat(earlier_iso)
        later = datetime.fromisoformat(later_iso)
    except (TypeError, ValueError):
        return float("inf")
    return (later - earlier).total_seconds()
```

Export from `backend/app/identity/__init__.py`:

```python
"""User identity: the session cookie and the user store."""

from .cookie import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie
from .models import User
from .store import UserStore

__all__ = ["COOKIE_MAX_AGE", "COOKIE_NAME", "SessionCookie", "User", "UserStore"]
```

- [ ] **Step 5: Add the settings**

In `backend/app/config.py`, beside `session_secret`:

```python
    guest_ttl_days: int = 7
    last_seen_throttle_seconds: float = 300.0
```

Read `GUEST_TTL_DAYS` from the environment in `from_env`, following the file's existing pattern for integer variables.

- [ ] **Step 6: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/identity/ -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: the identity tests PASS. Tests referencing `seed_if_empty` will fail — update them to `seed_user`, passing an explicit user id.

- [ ] **Step 7: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/app backend/tests
git commit -m "Add the user store: mint, load, touch, and expire guests"
```

---

### Task 5: The `current_user` dependency

Resolves the cookie to a user on every request, minting a guest when there is none, and sets the cookie on the response. Two routes are exempt: `/api/health` and `/api/stream/prices`. Without the exemption every crawler hit and every uptime probe mints a guest row, and prices are not user data.

**Files:**
- Modify: `backend/app/deps.py`, `backend/app/main.py`
- Test: `backend/tests/test_current_user.py` (create)

**Interfaces:**
- Consumes: `SessionCookie`, `UserStore`, `User` from `app.identity`
- Produces: `CurrentUserDep = Annotated[User, Depends(get_current_user)]`; `app.state.user_store` and `app.state.session_cookie`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_current_user.py`:

```python
"""Cookie -> user resolution, and the routes that must not mint one."""

from __future__ import annotations

from app.identity import COOKIE_NAME


class TestGuestMinting:
    def test_a_first_request_mints_a_guest_and_sets_the_cookie(self, api_client):
        response = api_client.get("/api/portfolio")

        assert response.status_code == 200
        assert COOKIE_NAME in response.cookies

    def test_the_cookie_is_httponly_lax_and_long_lived(self, api_client):
        response = api_client.get("/api/portfolio")

        header = response.headers["set-cookie"]
        assert "HttpOnly" in header
        assert "SameSite=Lax" in header
        assert "Max-Age=7776000" in header

    def test_the_same_cookie_returns_the_same_user(self, api_client):
        """The client keeps the cookie, so the second call must not mint."""
        api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})

        portfolio = api_client.get("/api/portfolio").json()

        assert len(portfolio["positions"]) == 1

    def test_a_tampered_cookie_gets_a_fresh_guest_rather_than_an_error(self, api_client):
        api_client.cookies.set(COOKIE_NAME, "not-a-valid-signature")

        response = api_client.get("/api/portfolio")

        assert response.status_code == 200
        assert response.json()["cash_balance"] == 10000.0


class TestExemptRoutes:
    def test_health_does_not_mint_a_guest(self, api_client):
        """Every uptime probe would otherwise create a row."""
        response = api_client.get("/api/health")

        assert response.status_code == 200
        assert COOKIE_NAME not in response.cookies

    def test_health_still_works_with_no_users_at_all(self, api_client):
        assert api_client.get("/api/health").json()["status"] == "ok"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_current_user.py -v
```

Expected: FAIL — no cookie is set, because nothing sets one yet.

- [ ] **Step 3: Write the dependency**

Replace the body of `backend/app/deps.py` with the accessors plus:

```python
async def get_current_user(request: Request, response: Response) -> User:
    """Resolve the caller, minting and seeding a guest when there is none.

    A cookie that does not verify -- tampered, signed with a rotated secret,
    or pointing at a row a database reset removed -- is treated exactly like
    no cookie at all. Handing back a 401 would be wrong: there is nothing to
    log in to yet, and the honest answer to an unreadable session is a fresh
    one.
    """
    store: UserStore = request.app.state.user_store
    cookie: SessionCookie = request.app.state.session_cookie

    user_id = cookie.verify(request.cookies.get(COOKIE_NAME))
    user = await store.get(user_id) if user_id else None

    if user is None:
        user = await store.mint_guest()
        _set_session_cookie(request, response, cookie, user.id)
    else:
        await store.touch(user)

    return user


def _set_session_cookie(
    request: Request, response: Response, cookie: SessionCookie, user_id: str
) -> None:
    """Attach the session cookie.

    `Secure` is set everywhere except localhost: a Secure cookie is dropped
    by the browser over plain http, which would make local development mint a
    new guest on every single request.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie.sign(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.hostname not in ("localhost", "127.0.0.1"),
        path="/",
    )


CurrentUserDep = Annotated["User", Depends(get_current_user)]
```

Add the imports it needs:

```python
from fastapi import Depends, Request, Response

from .identity import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie, User, UserStore
```

`User` and `UserStore` are needed at runtime here, not only for typing, so import them outside the `TYPE_CHECKING` block.

- [ ] **Step 4: Wire the store into the lifespan**

In `backend/app/main.py`, inside the `AsyncExitStack` after the migration block:

```python
        app.state.user_store = UserStore(db, settings)
        app.state.session_cookie = SessionCookie(settings.session_secret)
```

Add `from .identity import SessionCookie, UserStore` to the imports.

- [ ] **Step 5: Attach the dependency to the user-facing routes**

Add `user: CurrentUserDep` as a parameter to every handler in `app/portfolio/router.py`, `app/watchlist/router.py`, `app/llm/router.py`, `app/history/router.py`, and the `POST /api/reset` handler in `app/system/router.py`. The parameter is deliberately **unused** in this task — declaring it is what makes the dependency run, mint a guest, and set the cookie. Task 6 is what makes the services actually use it.

Mark it so linting does not object and the reason is on the page:

```python
@router.get("")
async def get_portfolio(service: TradeServiceDep, user: CurrentUserDep) -> dict:
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    view = await service.get_portfolio()
    return view.to_dict()
```

**Do not** add it to `GET /api/health` or `GET /api/stream/prices`. Every uptime probe and every crawler hit would otherwise mint a guest row, and prices are not user data.

- [ ] **Step 6: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_current_user.py -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: all PASS. Services still read the shared `default` user at this point, which is why the suite stays green — the cookie is being minted and set, but nothing reads it yet.

- [ ] **Step 7: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/app/deps.py backend/app/main.py backend/tests/test_current_user.py
git commit -m "Resolve a user from the session cookie on every request"
```

---

### Task 6: The reconciler goes global

`release_if_unheld()` currently asks whether *this* user still holds a ticker. With several users that stops the price feed for a ticker another user is holding — and `reconcile.py`'s own docstring names the consequence: valuation fails, or the position is silently valued at zero.

This lands before per-request scoping because the reconciler is shared state built once in the lifespan. Once services are per-request there is no per-user reconciler to build, so it must be repository-free first.

**Files:**
- Modify: `backend/app/reconcile.py`, `backend/app/main.py`, `backend/app/errors.py`, `backend/app/config.py`
- Test: `backend/tests/test_reconcile.py` (extend)

**Interfaces:**
- Produces:
  - `TickerReconciler(source: MarketDataSource, db: Database, capacity: int)` — no repositories
  - `MarketCapacityFullError` with `status_code, code = 503, "MARKET_CAPACITY_FULL"`
  - `Settings.market_capacity: int = 100`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_reconcile.py`:

```python
class TestGlobalTracking:
    async def test_the_union_spans_every_user(self, seeded_db, settings, price_cache):
        """One user's watchlist must not be the whole tracked set."""
        from app.identity.store import UserStore
        from app.market import MarketDataSource
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        store = UserStore(seeded_db, settings)
        first = await store.mint_guest()
        second = await store.mint_guest()
        await seeded_db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            ("w1", second.id, "PYPL", "2026-01-01T00:00:00Z"),
        )

        source = StubDataSource(price_cache)
        reconciler = TickerReconciler(source, seeded_db, settings.market_capacity)
        tracked = await reconciler.compute_tracked_tickers()

        assert "PYPL" in tracked
        assert "AAPL" in tracked  # seeded for both

    async def test_a_ticker_another_user_holds_is_not_released(
        self, seeded_db, settings, price_cache
    ):
        """The correctness trap: releasing here evicts the cached price, and
        the other user's position then values at zero or fails outright."""
        from app.identity.store import UserStore
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        store = UserStore(seeded_db, settings)
        holder = await store.mint_guest()
        await seeded_db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p1", holder.id, "NVDA", 4.0, 100.0, "2026-01-01T00:00:00Z"),
        )
        source = StubDataSource(price_cache)
        await source.add_ticker("NVDA")
        reconciler = TickerReconciler(source, seeded_db, settings.market_capacity)

        await reconciler.release_if_unheld("NVDA")

        assert "NVDA" in source.get_tickers()

    async def test_a_ticker_nobody_watches_or_holds_is_released(
        self, seeded_db, settings, price_cache
    ):
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        source = StubDataSource(price_cache)
        await source.add_ticker("ZZZZ")
        reconciler = TickerReconciler(source, seeded_db, settings.market_capacity)

        await reconciler.release_if_unheld("ZZZZ")

        assert "ZZZZ" not in source.get_tickers()


class TestGlobalCapacity:
    async def test_ensure_tracked_refuses_past_the_global_cap(
        self, seeded_db, settings, price_cache
    ):
        """A global limit reported as WATCHLIST_FULL would tell a user their
        own watchlist is full when it holds three tickers."""
        import pytest

        from app.errors import MarketCapacityFullError
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        source = StubDataSource(price_cache)
        for index in range(3):
            await source.add_ticker(f"T{index}")
        reconciler = TickerReconciler(source, seeded_db, capacity=3)

        with pytest.raises(MarketCapacityFullError):
            await reconciler.ensure_tracked("NEWT")

    async def test_a_ticker_already_tracked_is_allowed_at_capacity(
        self, seeded_db, settings, price_cache
    ):
        """At the cap, re-watching something already tracked costs nothing."""
        from app.reconcile import TickerReconciler
        from tests.conftest_services import StubDataSource

        source = StubDataSource(price_cache)
        for index in range(3):
            await source.add_ticker(f"T{index}")
        reconciler = TickerReconciler(source, seeded_db, capacity=3)

        await reconciler.ensure_tracked("T1")  # must not raise
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_reconcile.py -k "Global" -v
```

Expected: FAIL — `TickerReconciler` takes repositories, not a database, so construction raises `TypeError`.

- [ ] **Step 3: Add the error and the setting**

In `backend/app/errors.py`, beside `WatchlistFullError`:

```python
class MarketCapacityFullError(AppError):
    """The global tracked-ticker set is full.

    Deliberately distinct from WATCHLIST_FULL: this is a limit on what the
    whole deployment polls, not on the caller's own list. Reporting it as
    WATCHLIST_FULL would tell a user their watchlist is full when it holds
    three tickers.
    """

    status_code, code = 503, "MARKET_CAPACITY_FULL"
```

In `backend/app/config.py`, beside `watchlist_cap`:

```python
    #: Bounds simulator work and Massive polling cost across all users.
    market_capacity: int = 100
```

- [ ] **Step 4: Rewrite the reconciler**

Replace `backend/app/reconcile.py`'s class with:

```python
class TickerReconciler:
    """Owns the tracked-ticker set, globally.

    Both sides are global by necessity. The tracked set feeds one shared price
    cache, so "should we track this?" and "may we stop?" are questions about
    every user at once, not about whoever happens to be making the request.
    """

    def __init__(self, source: MarketDataSource, db: Database, capacity: int) -> None:
        self._source = source
        self._db = db
        self._capacity = capacity

    async def compute_tracked_tickers(self) -> list[str]:
        """Every watched ticker and every held ticker, across all users.

        Expired guests are deleted rows, so they drop out of this query on
        their own -- no liveness filter is needed.
        """
        rows = await self._db.fetch_all(
            "SELECT DISTINCT ticker FROM watchlist "
            "UNION "
            "SELECT DISTINCT ticker FROM positions WHERE quantity > ?",
            (EPSILON,),
        )
        return sorted(row["ticker"] for row in rows)

    async def ensure_tracked(self, ticker: str) -> None:
        """Start tracking a ticker if it is not already. Idempotent."""
        if ticker in self._source.get_tickers():
            return
        if len(self._source.get_tickers()) >= self._capacity:
            raise MarketCapacityFullError(
                f"The market data feed is tracking its maximum of {self._capacity} "
                f"tickers. Remove one from a watchlist before adding another."
            )
        await self._source.add_ticker(ticker)
        logger.info("Now tracking %s", ticker)

    async def release_if_unheld(self, ticker: str) -> None:
        """Stop tracking only when no user watches or holds the ticker.

        Removing a ticker also evicts its cached price, so releasing one that
        another user still holds makes their valuation fail -- or worse,
        silently value the position at zero.
        """
        row = await self._db.fetch_one(
            "SELECT 1 AS present FROM watchlist WHERE ticker = ? "
            "UNION ALL "
            "SELECT 1 AS present FROM positions WHERE ticker = ? AND quantity > ? "
            "LIMIT 1",
            (ticker, ticker, EPSILON),
        )
        if row is not None:
            logger.info("Keeping %s tracked: another user watches or holds it", ticker)
            return
        await self._source.remove_ticker(ticker)
        logger.info("Stopped tracking %s", ticker)

    async def reconcile(self) -> list[str]:
        """Force the source's tracked set to match the global union exactly."""
        target = set(await self.compute_tracked_tickers())
        current = set(self._source.get_tickers())

        for ticker in sorted(target - current):
            await self._source.add_ticker(ticker)
        for ticker in sorted(current - target):
            await self._source.remove_ticker(ticker)

        return sorted(target)
```

Update the imports at the top of the file — it now needs `Database` and `MarketCapacityFullError`, and no longer needs either repository:

```python
from .db import Database
from .errors import MarketCapacityFullError
from .market import MarketDataSource
from .portfolio.models import EPSILON
```

`EPSILON` is `1e-9`, defined at `app/portfolio/models.py:12` — verified against the file, not assumed. Import it; never redefine it.

Also update the module docstring: it currently describes the rule as being about "the user", which is no longer true.

- [ ] **Step 5: Update construction in the lifespan**

In `backend/app/main.py`:

```python
        reconciler = TickerReconciler(source, db, settings.market_capacity)
```

- [ ] **Step 6: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_reconcile.py -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: PASS. Existing reconciler tests that construct it with repositories need updating to the new signature.

- [ ] **Step 7: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/
git commit -m "Make the ticker reconciler global across users"
```

---

### Task 7: The snapshot writer covers active users

The container task writes one snapshot for one user. It must iterate the users seen in the last hour instead. The serverless path is a separate problem: it writes a snapshot from the SSE heartbeat, and the stream has no user to attribute one to — so it moves to `GET /api/portfolio`, which is naturally scoped to an active user.

Like Task 6, this lands before per-request scoping because the writer is a background task built in the lifespan.

**Files:**
- Modify: `backend/app/portfolio/snapshot_writer.py`, `backend/app/portfolio/service.py`, `backend/app/portfolio/router.py`, `backend/app/market/stream.py`, `backend/app/main.py`
- Test: `backend/tests/portfolio/test_snapshot_writer.py` (extend)

**Interfaces:**
- Consumes: `UserStore.list_active_since(iso_cutoff)` from Task 4
- Produces:
  - `SnapshotWriter(db, settings, user_store, price_cache, interval, retention_days)` — builds its own per-user services
  - `TradeService.write_snapshot_if_stale() -> bool`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/portfolio/test_snapshot_writer.py`:

```python
class TestCoversActiveUsers:
    async def test_a_snapshot_is_written_for_every_recently_seen_user(
        self, seeded_db, settings, priced_cache
    ):
        from app.identity.store import UserStore
        from app.portfolio.snapshot_writer import SnapshotWriter

        store = UserStore(seeded_db, settings)
        first = await store.mint_guest()
        second = await store.mint_guest()
        writer = SnapshotWriter(seeded_db, settings, store, priced_cache)

        await writer.write_for_active_users()

        for user in (first, second):
            rows = await seeded_db.fetch_all(
                "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?",
                (user.id,),
            )
            assert len(rows) == 1

    async def test_an_idle_user_gets_no_snapshot(
        self, seeded_db, settings, priced_cache
    ):
        """Writing for every user forever turns a dormant demo into a growing
        write load with nobody reading the result."""
        from app.identity.store import UserStore
        from app.portfolio.snapshot_writer import SnapshotWriter

        store = UserStore(seeded_db, settings)
        idle = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", idle.id),
        )
        writer = SnapshotWriter(seeded_db, settings, store, priced_cache)

        await writer.write_for_active_users()

        rows = await seeded_db.fetch_all(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?", (idle.id,)
        )
        assert rows == []

    async def test_one_user_failing_does_not_stop_the_others(
        self, seeded_db, settings, priced_cache
    ):
        """A single unpriceable position must not cost every other user their
        snapshot for that interval."""
        from app.identity.store import UserStore
        from app.portfolio.snapshot_writer import SnapshotWriter

        store = UserStore(seeded_db, settings)
        broken = await store.mint_guest()
        healthy = await store.mint_guest()
        await seeded_db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p-broken", broken.id, "NOPRICE", 1.0, 10.0, "2026-01-01T00:00:00Z"),
        )
        writer = SnapshotWriter(seeded_db, settings, store, priced_cache)

        await writer.write_for_active_users()

        rows = await seeded_db.fetch_all(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = ?",
            (healthy.id,),
        )
        assert len(rows) == 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/portfolio/test_snapshot_writer.py -k Active -v
```

Expected: FAIL — `SnapshotWriter` takes a `TradeService`, so construction raises `TypeError`.

- [ ] **Step 3: Rewrite the writer**

Replace the constructor and add the new method in `backend/app/portfolio/snapshot_writer.py`:

```python
class SnapshotWriter:
    """Writes a portfolio snapshot per active user on an interval.

    Builds its own per-user services rather than receiving one: there is no
    single user at startup any more, and the set changes between ticks.
    """

    def __init__(
        self,
        db: Database,
        settings: Settings,
        user_store: UserStore,
        price_cache: PriceCache,
        interval: float = 30.0,
        retention_days: int = 7,
    ) -> None:
        self._db = db
        self._settings = settings
        self._users = user_store
        self._price_cache = price_cache
        self._interval = interval
        self._retention_days = retention_days
        self._task: asyncio.Task | None = None

    async def write_for_active_users(self) -> int:
        """Snapshot every user seen within the last hour. Returns the count.

        One user's failure is caught and logged rather than raised: an
        unpriceable position in one portfolio must not cost every other user
        their snapshot for this interval.
        """
        cutoff = iso_seconds_ago(3600)
        written = 0
        for user_id in await self._users.list_active_since(cutoff):
            try:
                await self._write_one(user_id)
                written += 1
            except Exception:
                logger.exception("Snapshot failed for %s", user_id)
        return written

    async def _write_one(self, user_id: str) -> None:
        service = build_trade_service(
            self._db, self._settings, self._price_cache, user_id
        )
        await service.write_snapshot()
```

Update `start()` and `_run_loop()` to call `write_for_active_users()` in place of `self._service.write_snapshot()`, and pruning to run across all users:

```python
    async def start(self) -> None:
        """Write immediately, then start the periodic task.

        The immediate write means a returning user's P&L chart has a point at
        t=0 rather than being empty for the first interval.
        """
        await self.write_for_active_users()
        self._task = asyncio.create_task(self._run_loop(), name="snapshot-writer")
        logger.info("Snapshot writer started (every %.0fs)", self._interval)
```

Add a `build_trade_service(db, settings, price_cache, user_id)` helper. Put it in `backend/app/portfolio/service.py` so both this writer and `deps.py` use one construction path — a second, subtly different one is how a repository ends up unscoped:

```python
def build_trade_service(
    db: Database,
    settings: Settings,
    price_cache: PriceCache,
    user_id: str,
    reconciler: TickerReconciler | None = None,
    lock: asyncio.Lock | None = None,
) -> TradeService:
    """Construct a TradeService for one user.

    The single place repositories are wired to a user id, so there is one
    place to get it wrong rather than three.
    """
    return TradeService(
        db,
        UserRepository(db, user_id),
        PositionRepository(db, user_id),
        TradeRepository(db, user_id),
        SnapshotRepository(db, user_id),
        price_cache,
        reconciler,
        lock or asyncio.Lock(),
    )
```

Add `iso_seconds_ago(seconds: int) -> str` to `backend/app/clock.py` beside `utcnow_iso()`, returning an ISO-8601 UTC string that many seconds in the past.

- [ ] **Step 4: Move the serverless snapshot onto the portfolio read**

Add to `TradeService` in `backend/app/portfolio/service.py`:

```python
    async def write_snapshot_if_stale(self) -> bool:
        """Write a snapshot when the newest is older than the interval.

        The serverless path: nothing runs between requests, so this replaces
        the SSE heartbeat, which no longer has a user to attribute a snapshot
        to. Naturally scoped to users who are actually looking at the app.
        """
        newest = await self._snapshots.newest_recorded_at()
        if newest is not None:
            age = _seconds_since(newest)
            if age < self._settings.snapshot_interval_seconds:
                return False
        await self.write_snapshot()
        return True
```

Add `newest_recorded_at() -> str | None` to `SnapshotRepository`:

```python
    async def newest_recorded_at(self) -> str | None:
        row = await self._db.fetch_one(
            "SELECT recorded_at FROM portfolio_snapshots WHERE user_id = ? "
            "ORDER BY recorded_at DESC, seq DESC LIMIT 1",
            (self._user_id,),
        )
        return row["recorded_at"] if row is not None else None
```

In `backend/app/portfolio/router.py`, call it from the portfolio read when serverless:

```python
@router.get("")
async def get_portfolio(request: Request, service: TradeServiceDep) -> dict:
    if request.app.state.settings.serverless:
        await service.write_snapshot_if_stale()
    view = await service.get_portfolio()
    return view.to_dict()
```

- [ ] **Step 5: Delete the heartbeat plumbing**

In `backend/app/market/stream.py`, remove the `on_heartbeat` and `heartbeat_seconds` parameters from both `create_stream_router` and the generator below it, along with the block that calls `on_heartbeat`. In `backend/app/main.py`, delete `write_snapshot_from_stream` and the `on_heartbeat=` argument.

The stream now has no user and needs none — which is why it is exempt from user resolution.

- [ ] **Step 6: Update lifespan construction**

```python
            snapshot_writer = SnapshotWriter(
                db,
                settings,
                app.state.user_store,
                price_cache,
                settings.snapshot_interval_seconds,
                settings.snapshot_retention_days,
            )
            await snapshot_writer.start()
            stack.push_async_callback(snapshot_writer.stop)
```

- [ ] **Step 7: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/portfolio/ -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: PASS. Stream tests asserting on heartbeat behaviour must be deleted, not adapted — the behaviour is gone.

- [ ] **Step 8: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/
git commit -m "Snapshot every active user, and drop the SSE heartbeat"
```

---

### Task 8: Per-request services, and the death of `DEFAULT_USER_ID`

The centre of this phase. Services move from singletons built once in the lifespan to per-request factories scoped to the calling user, and every `user_id` default is deleted so an unscoped repository cannot be constructed at all.

The isolation tests come first. The spec is explicit that they are written before the scoping change rather than after it, and they are the highest-value tests in the suite: they are the only thing standing between this design and one user reading another's portfolio.

Tasks 6 and 7 removed the two things that would otherwise block this — the reconciler and the snapshot writer are now global and repository-free, so nothing in the lifespan needs a user any more.

**Files:**
- Modify: `backend/app/deps.py`, `backend/app/main.py`, `backend/app/db/connection.py`, `backend/app/db/seed.py`, `backend/app/db/__init__.py`
- Modify: `backend/app/portfolio/repository.py`, `backend/app/watchlist/repository.py`, `backend/app/llm/repository.py`
- Modify: `backend/app/portfolio/router.py`, `backend/app/watchlist/router.py`, `backend/app/llm/router.py`
- Test: `backend/tests/test_cross_user_isolation.py` (create), `backend/tests/conftest.py`

**Interfaces:**
- Consumes: `CurrentUserDep` (Task 5), `build_trade_service(...)` (Task 7)
- Produces: `TradeServiceDep`, `WatchlistServiceDep`, `ChatServiceDep` — per-request, user-scoped, same names so routers need no import changes

- [ ] **Step 1: Add a two-user fixture**

In `backend/tests/conftest.py`:

```python
@pytest.fixture
def second_client(settings):
    """A second TestClient with its own cookie jar, sharing one database.

    Two real sessions rather than two hand-built repositories: the scoping has
    to hold through the dependency wiring, not just in a constructor.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as client:
        yield client
```

It takes the same `settings` as `api_client`, so both share a schema. Different settings would give each its own database and the tests would prove nothing.

- [ ] **Step 2: Write the failing isolation tests**

Create `backend/tests/test_cross_user_isolation.py`:

```python
"""User A must not read or mutate user B's rows.

The highest-value tests in this suite. Every other test checks that a feature
works; these check that it does not work on someone else's data. A regression
here is not a bug report, it is a privacy incident -- so they drive two real
HTTP sessions rather than two hand-built repositories, because the scoping has
to hold through the whole dependency chain.
"""

from __future__ import annotations


class TestPortfolioIsolation:
    def test_a_trade_by_one_user_is_invisible_to_another(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
        )

        other = second_client.get("/api/portfolio").json()

        assert other["positions"] == []
        assert other["cash_balance"] == 10000.0

    def test_spending_cash_does_not_spend_anyone_else_s(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 1, "side": "buy"},
        )

        assert api_client.get("/api/portfolio").json()["cash_balance"] < 10000.0
        assert second_client.get("/api/portfolio").json()["cash_balance"] == 10000.0


class TestWatchlistIsolation:
    def test_an_added_ticker_does_not_appear_for_another_user(
        self, api_client, second_client
    ):
        api_client.post("/api/watchlist", json={"ticker": "PYPL"})

        assert "PYPL" not in second_client.get("/api/watchlist").json()["tickers"]

    def test_a_removed_ticker_stays_for_another_user(self, api_client, second_client):
        api_client.delete("/api/watchlist/AAPL")

        assert "AAPL" in second_client.get("/api/watchlist").json()["tickers"]


class TestChatIsolation:
    def test_chat_history_is_not_shared(self, api_client, second_client):
        api_client.post("/api/chat", json={"message": "isolation probe"})

        theirs = second_client.get("/api/chat").json()

        assert all("isolation probe" not in m["content"] for m in theirs["messages"])


class TestResetIsolation:
    def test_a_reset_does_not_wipe_another_user(self, api_client, second_client):
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 3, "side": "buy"},
        )

        api_client.post("/api/reset")

        survivor = second_client.get("/api/portfolio").json()
        assert len(survivor["positions"]) == 1
        assert survivor["positions"][0]["ticker"] == "AAPL"
```

Check every response shape against `planning/API_CONTRACT.md` before running. If an assertion disagrees with the contract, fix the assertion — the contract is frozen.

- [ ] **Step 3: Run them to verify they fail**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_cross_user_isolation.py -v
```

Expected: **every one FAILS**, because both clients still share the `default` user. A test here that passes before the change is measuring nothing.

- [ ] **Step 4: Delete the defaults**

In `backend/app/portfolio/repository.py`, `backend/app/watchlist/repository.py`, and `backend/app/llm/repository.py`, change all six constructors — `UserRepository`, `PositionRepository`, `TradeRepository`, `SnapshotRepository`, `WatchlistRepository`, `ChatRepository`:

```python
    def __init__(self, db: Database, user_id: str) -> None:
```

Remove `DEFAULT_USER_ID` from each file's imports.

In `backend/app/db/connection.py`, delete the `DEFAULT_USER_ID` assignment and fix the module docstring, which calls it "the shared user id". In `backend/app/db/seed.py`, delete the transitional `seed_if_empty`. In `backend/app/db/__init__.py`, remove both from the exports.

- [ ] **Step 5: Write the per-request factories**

Replace the service accessors in `backend/app/deps.py`:

```python
def get_trade_service(request: Request, user: CurrentUserDep) -> TradeService:
    """Build a TradeService scoped to the calling user.

    Per-request construction is what makes the user id a required argument
    everywhere below it. The pool, price cache, source, reconciler and locks
    are shared; only the repositories are per-user.
    """
    state = request.app.state
    return build_trade_service(
        state.db,
        state.settings,
        state.price_cache,
        user.id,
        reconciler=state.reconciler,
        lock=state.trade_lock,
    )


def get_watchlist_service(request: Request, user: CurrentUserDep) -> WatchlistService:
    state = request.app.state
    return WatchlistService(
        state.db,
        WatchlistRepository(state.db, user.id),
        state.reconciler,
        state.watchlist_lock,
        state.settings.watchlist_cap,
    )


def get_chat_service(
    request: Request,
    user: CurrentUserDep,
    trades: TradeServiceDep,
    watchlist: WatchlistServiceDep,
) -> ChatService:
    """Depends on the two service dependencies rather than rebuilding them, so
    a chat-driven trade goes through the same locked service a manual one does.
    """
    state = request.app.state
    return ChatService(
        ChatRepository(state.db, user.id),
        trades,
        watchlist,
        state.chat_client,
        ActionExecutor(trades, watchlist),
        state.settings,
    )
```

Keep the existing `Annotated` alias names so no router import changes:

```python
TradeServiceDep = Annotated["TradeService", Depends(get_trade_service)]
WatchlistServiceDep = Annotated["WatchlistService", Depends(get_watchlist_service)]
ChatServiceDep = Annotated["ChatService", Depends(get_chat_service)]
```

- [ ] **Step 6: Strip the lifespan to shared state**

In `backend/app/main.py`, delete the construction of `users`, `positions`, `trades`, `snapshots`, `watchlist_repo`, `chat_repo`, `trade_service`, `watchlist_service`, `chat_service` and `reset_service`, and delete the `seed_if_empty` call with its import. Keep on `app.state`: `db`, `settings`, `price_cache`, `source`, `history_store`, `reconciler`, `user_store`, `session_cookie`, `trade_lock`, `watchlist_lock`, and add:

```python
        app.state.chat_client = create_chat_client(settings)
```

The two locks stay process-wide. A per-request lock would serialize nothing — it exists to order concurrent writes within one instance, which is precisely what a fresh lock per request cannot do.

A fresh database now has no users at all until the first request mints one. That is correct: there is no "the" user any more.

- [ ] **Step 7: Drop the `del user` placeholders**

The handlers changed in Task 5 declared `user: CurrentUserDep` purely for its side effect. The services are now scoped through their own dependency, so remove the unused parameter and its `del user` line from every handler that does not otherwise need it. `POST /api/reset` keeps needing it — Task 9.

- [ ] **Step 8: Run the isolation tests, then everything**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_cross_user_isolation.py -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: every isolation test PASSES. Other tests that construct a repository without a user now raise `TypeError` — update each by passing an explicit user id. **Never** by reintroducing a default; that is the one change this entire task exists to prevent.

`tests/conftest_services.py` needs a user id threaded through `Services`; add a `user_id` argument rather than defaulting one inside it.

- [ ] **Step 9: Prove the constant is gone**

```bash
cd backend && grep -rn "DEFAULT_USER_ID" app/ && echo "STILL PRESENT -- not done" || echo "gone"
cd backend && grep -rn "user_id: str = " app/ && echo "A DEFAULT SURVIVES -- not done" || echo "no user_id defaults"
```

Expected: `gone` and `no user_id defaults`.

- [ ] **Step 10: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/
git commit -m "Scope every service to the calling user"
```

---

### Task 9: `ResetService` is scoped to its caller

Reset must wipe the caller's rows and nobody else's, then trigger a **global** reconcile — the tickers it released may still be watched or held by other users.

**Files:**
- Modify: `backend/app/system/service.py`, `backend/app/system/router.py`, `backend/app/deps.py`
- Test: `backend/tests/system/test_reset_scope.py` (create)

**Interfaces:**
- Produces: `ResetServiceDep`, and `ResetService(db, settings, user_id, price_cache, reconciler, history_store, trade_lock, watchlist_lock)`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/system/test_reset_scope.py`:

```python
"""Reset wipes one user, and reconciles for everyone."""

from __future__ import annotations


class TestResetTouchesOnlyTheCaller:
    def test_another_user_keeps_their_watchlist_edits(self, api_client, second_client):
        second_client.post("/api/watchlist", json={"ticker": "PYPL"})

        api_client.post("/api/reset")

        assert "PYPL" in second_client.get("/api/watchlist").json()["tickers"]

    def test_another_user_keeps_their_cash(self, api_client, second_client):
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 2, "side": "buy"},
        )
        spent = second_client.get("/api/portfolio").json()["cash_balance"]

        api_client.post("/api/reset")

        assert second_client.get("/api/portfolio").json()["cash_balance"] == spent

    def test_the_caller_is_restored_to_the_seeded_state(self, api_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 2, "side": "buy"},
        )

        body = api_client.post("/api/reset").json()

        assert body["cash_balance"] == 10000.0
        assert body["positions"] == []
        assert len(api_client.get("/api/watchlist").json()["tickers"]) == 10


class TestResetKeepsOthersTracked:
    def test_a_ticker_another_user_holds_stays_priced_after_a_reset(
        self, api_client, second_client
    ):
        """Reset releases the caller's tickers; a global reconcile is what
        stops that from evicting a price someone else's position needs."""
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "NVDA", "quantity": 1, "side": "buy"},
        )

        api_client.post("/api/reset")

        portfolio = second_client.get("/api/portfolio").json()
        assert portfolio["positions"][0]["current_price"] is not None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/system/test_reset_scope.py -v
```

Expected: FAIL — reset currently wipes the shared user, so the second client loses its data too.

- [ ] **Step 3: Scope the service**

Rewrite `ResetService.__init__` to take `user_id` and build its own repositories, and rewrite `reset()`:

```python
    async def reset(self) -> None:
        """Wipe this user's state, re-seed them, and reconcile globally."""
        async with self._trade_lock, self._watchlist_lock:
            # Delete and re-seed in ONE transaction: the profile row must never
            # be committed-absent, because every per-user table has a foreign
            # key pointing at it and a concurrent insert would then fail.
            async with self._db.transaction():
                await self._positions.delete_all()
                await self._trades.delete_all()
                await self._snapshots.delete_all()
                await self._chat.delete_all()
                await self._watchlist.delete_all()
                await self._db.execute(
                    "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                    (self._settings.initial_cash, self._user_id),
                )
                await seed_user(self._db, self._settings, self._user_id)
                await self._snapshots.insert(self._settings.initial_cash)

            # Global, not per-user: this user's released tickers may still be
            # watched or held by someone else, and reconcile() is the only
            # thing that checks.
            await self._reconciler.reconcile()
            self._history.clear()
```

The profile row is now **updated**, not deleted and recreated — deleting it would cascade the user out of existence and invalidate their cookie. That is a behaviour change from phase 1, where the row was recreated by `seed_if_empty`, and it is what keeps a reset from silently logging the user out.

- [ ] **Step 4: Add the dependency and use it**

In `backend/app/deps.py`:

```python
def get_reset_service(request: Request, user: CurrentUserDep) -> ResetService:
    state = request.app.state
    return ResetService(
        state.db,
        state.settings,
        user.id,
        state.price_cache,
        state.reconciler,
        state.history_store,
        state.trade_lock,
        state.watchlist_lock,
    )


ResetServiceDep = Annotated["ResetService", Depends(get_reset_service)]
```

In `backend/app/system/router.py`:

```python
@router.post("/reset")
async def reset(service: TradeServiceDep, reset_service: ResetServiceDep) -> dict:
    """Restore this user's seeded starting state and return their portfolio."""
    await reset_service.reset()
    view = await service.get_portfolio()
    return view.to_dict()
```

- [ ] **Step 5: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/system/ -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

Expected: PASS. `tests/system/test_reset_atomicity.py` from phase 1 asserts the profile is never committed-absent; it must still pass, and the `UPDATE` makes that strictly easier to satisfy.

- [ ] **Step 6: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/
git commit -m "Scope reset to the calling user"
```

---

### Task 10: Guest cleanup

Idle guests accumulate forever otherwise — every crawler that gets past the route exemptions, every abandoned session. The foreign keys added in phase 1 make expiry a single `DELETE`.

**Files:**
- Create: `backend/app/system/cleanup.py`
- Modify: `backend/app/system/router.py`, `backend/app/main.py`, `backend/app/config.py`, `vercel.json`, `.env.example`
- Test: `backend/tests/test_guest_cleanup.py` (create)

**Interfaces:**
- Consumes: `UserStore.delete_expired_guests(iso_cutoff)` (Task 4)
- Produces: `GuestCleaner(user_store, settings, interval_seconds)` with `.start()`, `.stop()`, `.run_once() -> int`; `POST /api/admin/cleanup`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_guest_cleanup.py`:

```python
"""Idle guests expire; signed-in users never do."""

from __future__ import annotations


class TestCleanupRoute:
    def test_the_route_is_refused_without_the_secret(self, api_client):
        assert api_client.post("/api/admin/cleanup").status_code in (401, 403)

    def test_the_route_is_refused_with_the_wrong_secret(self, api_client):
        response = api_client.post(
            "/api/admin/cleanup", headers={"X-Cleanup-Secret": "wrong"}
        )
        assert response.status_code in (401, 403)


class TestCleaner:
    async def test_run_once_deletes_only_expired_guests(self, seeded_db, settings):
        from app.identity.store import UserStore
        from app.system.cleanup import GuestCleaner

        store = UserStore(seeded_db, settings)
        stale = await store.mint_guest()
        fresh = await store.mint_guest()
        await seeded_db.execute(
            "UPDATE users_profile SET last_seen_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", stale.id),
        )

        deleted = await GuestCleaner(store, settings).run_once()

        assert deleted == 1
        assert await store.get(stale.id) is None
        assert await store.get(fresh.id) is not None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_guest_cleanup.py -v
```

Expected: FAIL — the route 404s and `app.system.cleanup` does not exist.

- [ ] **Step 3: Write the cleaner**

Create `backend/app/system/cleanup.py`:

```python
"""Expiring idle guests.

A daily task in the container. On Vercel nothing runs between requests, so a
Cron entry posts to the admin route instead.
"""

from __future__ import annotations

import asyncio
import logging

from ..clock import iso_seconds_ago
from ..config import Settings
from ..identity import UserStore

logger = logging.getLogger(__name__)


class GuestCleaner:
    """Deletes guests idle past the TTL. The foreign keys cascade the rest."""

    def __init__(
        self, user_store: UserStore, settings: Settings, interval_seconds: float = 86400.0
    ) -> None:
        self._users = user_store
        self._settings = settings
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    async def run_once(self) -> int:
        cutoff = iso_seconds_ago(self._settings.guest_ttl_days * 86400)
        return await self._users.delete_expired_guests(cutoff)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop(), name="guest-cleanup")
        logger.info("Guest cleanup started (every %.0fs)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.run_once()
            except Exception:
                # Never let a cleanup failure take the process down.
                logger.exception("Guest cleanup failed")
```

- [ ] **Step 4: Add the guarded route**

In `backend/app/system/router.py`:

```python
@router.post("/admin/cleanup")
async def cleanup(request: Request) -> dict:
    """Expire idle guests. Driven by Vercel Cron where no background task runs.

    Guarded by a shared secret rather than by user identity: there is no admin
    user in this app, and the endpoint must be callable by a scheduler.
    """
    secret = request.app.state.settings.cleanup_secret
    supplied = request.headers.get("X-Cleanup-Secret", "")
    if not secret or not secrets.compare_digest(supplied, secret):
        raise CleanupForbiddenError("Cleanup requires a valid X-Cleanup-Secret header.")
    deleted = await GuestCleaner(
        request.app.state.user_store, request.app.state.settings
    ).run_once()
    return {"deleted": deleted}
```

`secrets.compare_digest` rather than `==`: a plain comparison leaks the secret's length and prefix through timing. An unset `cleanup_secret` refuses every call, which is the safe default for a route that deletes rows.

Add `CleanupForbiddenError` to `backend/app/errors.py`:

```python
class CleanupForbiddenError(AppError):
    status_code, code = 403, "CLEANUP_FORBIDDEN"
```

Add `cleanup_secret: str = ""` to `Settings`, read from `CLEANUP_SECRET`.

- [ ] **Step 5: Start it in the container only**

In `backend/app/main.py`, beside the snapshot writer:

```python
        if not settings.serverless:
            cleaner = GuestCleaner(app.state.user_store, settings)
            await cleaner.start()
            stack.push_async_callback(cleaner.stop)
```

- [ ] **Step 6: Add the Vercel Cron entry**

In `vercel.json`, alongside the existing keys:

```json
  "crons": [{ "path": "/api/admin/cleanup", "schedule": "0 4 * * *" }]
```

Vercel Cron issues a GET, so also accept GET on the route (`@router.api_route("/admin/cleanup", methods=["GET", "POST"])`) — verify this against current Vercel Cron documentation before implementing, and keep the secret check on both methods.

In `.env.example`:

```bash
# Guards POST /api/admin/cleanup, which deletes idle guest accounts.
# Unset, the endpoint refuses every call.
CLEANUP_SECRET=

# How many idle days before a guest account and its data are deleted.
GUEST_TTL_DAYS=7
```

- [ ] **Step 7: Run the tests and the whole suite**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest tests/test_guest_cleanup.py -v
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev pytest -q
```

- [ ] **Step 8: Verify formatting and lint, then commit**

```bash
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff format --check app/ tests/
cd backend && UV_CACHE_DIR=$TMPDIR/uvcache uv run --extra dev ruff check app/ tests/
git add backend/ vercel.json .env.example
git commit -m "Expire idle guest accounts"
```

---

### Task 11: Documentation

The app is multi-user now and several documents say it is not. Phase 1 produced four factually wrong statements in a single documentation pass, every one written from memory of the code rather than from the code — so every claim below gets checked against the file that implements it before it is written.

**Files:**
- Modify: `README.md`, `planning/PLAN.md`, `planning/API_CONTRACT.md`, `planning/DECISIONS.md`, `planning/BACKEND_SUMMARY.md`, `planning/VERCEL_DEPLOYMENT.md`, `backend/CLAUDE.md`

- [ ] **Step 1: Update the shipped-state documents in place**

- `README.md` — the quick start still works with no configuration, but `SESSION_SECRET` matters in production. State plainly that leaving it unset regenerates it per restart, which signs out every user and **permanently orphans every guest portfolio**, because the cookie is the only pointer to the row. Document `GUEST_TTL_DAYS` and `CLEANUP_SECRET`.
- `planning/API_CONTRACT.md` — add `MARKET_CAPACITY_FULL` (503) and `CLEANUP_FORBIDDEN` (403) to the error table. Document the `trader_session` cookie and note that `/api/health` and `/api/stream/prices` never set it. Add `POST /api/admin/cleanup`.
- `planning/BACKEND_SUMMARY.md` — replace the single-user description of service construction with the per-request factory model.
- `planning/VERCEL_DEPLOYMENT.md` — the snapshot no longer rides the SSE heartbeat; it is written during `GET /api/portfolio` when the newest is stale. Document the Cron entry.
- `backend/CLAUDE.md` — `DEFAULT_USER_ID` is gone; repositories require a user id.

- [ ] **Step 2: Add dated supersession notes to the provenance documents**

`planning/PLAN.md` and `planning/DECISIONS.md` record why past decisions were made. Do not silently rewrite them — add a dated note the way phase 1 did:

- `planning/PLAN.md` §7 — the schema section states every table's `user_id` defaults to `"default"` and calls this "hardcoded for now (single-user)". Add a note dated 2026-08-24 recording that per-user scoping landed, `DEFAULT_USER_ID` is deleted, and rows now belong to minted users.
- `planning/DECISIONS.md` — any decision resolved on single-user assumptions gets a note pointing at the spec, not an edit.

- [ ] **Step 3: Verify every claim against the code**

For each statement asserting a mechanism, open the file that implements it and confirm. Specifically re-check: the cookie's flags against `deps.py`; the exempt routes against the routers; the throttle window against `config.py`; the caps (25 per-user, 100 global) against `config.py`; the cleanup schedule against `vercel.json`.

A plausible-sounding invented rationale is harder to catch later than an obviously stale sentence. Phase 1's worst example explained the advisory lock as serialising "the Docker target's multiple worker connections" — entirely plausible, and wrong, because Docker runs a single process.

- [ ] **Step 4: Confirm nothing claims phase 3 is built**

```bash
grep -rn "OAuth\|sign in\|sign-in\|Google\|GitHub" README.md planning/*.md | grep -v "phase 3\|not yet\|planned"
```

Anything that reads as shipped must be reworded as planned. There is no way to sign in after this phase.

- [ ] **Step 5: Commit**

```bash
git add README.md planning/ backend/CLAUDE.md
git commit -m "Document per-user scoping"
```

---

## Self-Review

**Spec coverage.** §6's request path is Tasks 3–5 and 8; the `main.py` reduction to shared state is Task 8 Step 6; the `DEFAULT_USER_ID` deletion is Task 8 Step 4 and is verified by grep in Step 9; the route exemptions are Task 5 Step 5 with tests in Task 5 Step 1; `last_seen_at` throttling is Task 4. §7.1's reconciler is Task 6, including the `MARKET_CAPACITY_FULL` / `WATCHLIST_FULL` distinction. §7.2's snapshot writer and the heartbeat deletion are Task 7. §7.3's reset is Task 9. §7.4's cleanup is Task 10. §4's `kind` and `last_seen_at` are Task 2. §3's cookie is Task 3. §11's isolation tests are Task 8 Step 2 and the migrated fixture is Task 1.

**Deliberately deferred to phase 3, with no task here:** `oauth_identities`, the `email` / `display_name` / `avatar_url` columns, every `/api/auth/*` route, `AUTH_MOCK`, `PUBLIC_BASE_URL`, the claim flow, and all frontend work. Each has no reader until sign-in exists.

**Ordering.** Tasks 6 and 7 precede Task 8 because the reconciler and snapshot writer are lifespan-built shared state; leaving them per-user would force Task 8 to invent a user for startup. An earlier draft of this plan had them after, which produced exactly that hedge. Task 4 keeps `seed_if_empty` as a transitional wrapper so Tasks 4–7 each end with a green suite; Task 8 deletes it.

**Known risk.** Task 8 will break many existing tests, by design — every repository constructed without a user now raises `TypeError`. That is the intended blast radius, and the instruction is always to pass an explicit user id, never to restore a default.
