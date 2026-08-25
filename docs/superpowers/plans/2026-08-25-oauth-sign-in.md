# OAuth Sign-In Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a visitor attach their guest portfolio to a Google or GitHub account so it survives a change of browser, without taking away the zero-friction first run.

**Architecture:** Authlib's Starlette OAuth client runs inside the existing FastAPI app; sign-in is a full-page navigation, which is what makes it work from a static export with no Node runtime. A row in `users_profile` is promoted in place (`kind='guest'` → `'user'`) when an untouched guest signs in, and the cookie is repointed at the existing account when that provider identity is already known. The one case that cannot be decided server-side — a guest with real activity signing into an account that already exists — redirects with a short-lived signed token and asks.

**Tech Stack:** FastAPI, Authlib (`authlib.integrations.starlette_client`), Starlette `SessionMiddleware` for PKCE state, `itsdangerous` for the claim token, Postgres/asyncpg, Next.js static export + Zustand.

**Spec:** `docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md` — §5 (OAuth), §5.1 (identity resolution), §5.2 (the contested claim), §9 (frontend), §10 (configuration), §11 (testing). This is step 3 of the spec's build order (§13); steps 1 and 2 are merged.

## Global Constraints

- **Providers are optional.** With no credentials configured the app must behave exactly as it does today: guest-only, no sign-in button, `docker compose up` unchanged. A login route for an unconfigured provider is `404 AUTH_PROVIDER_UNAVAILABLE`.
- **D-6: identities are never matched by email.** Lookup is `(provider, provider_user_id)` only. Email is stored for display and never for resolution.
- **D-2: on a collision the existing account wins.** Guest activity is discarded after confirmation. Never merge — merging mints unlimited starting cash.
- **Every failure uses the envelope in `backend/app/errors.py`.** New codes: `AUTH_PROVIDER_UNAVAILABLE` (404), `AUTH_STATE_INVALID` (400), `AUTH_EXCHANGE_FAILED` (502), `CLAIM_TOKEN_INVALID` (400). No route builds an error body by hand.
- **PKCE state lives in a cookie, not process memory.** Serverless instances share nothing; an in-memory state store fails intermittently and unreproducibly.
- **Every new dependency goes in BOTH `backend/pyproject.toml` and the root `requirements.txt`.** `backend/tests/test_vercel_requirements.py` fails the build otherwise — that guard exists because this exact drift took production down on 2026-08-25.
- **`user_id` is never defaulted.** `DEFAULT_USER_ID` is deleted; every repository takes an explicit user. Nothing in this plan reintroduces a default.
- **Visual work stays inside PLAN.md §2/§10:** system materials, systemBlue as the only interaction colour, provider buttons in the neutral fill rather than Google or GitHub brand colours, no new palette tokens. Any new foreground/background pairing goes into `frontend/__tests__/lib/theme.test.ts`.
- **Tests:** `cd backend && uv run pytest` (needs `TEST_DATABASE_URL`, default `postgresql://trader:trader@localhost:5432/trader`); `cd frontend && npm test`. Lint with `uv run ruff check .` and `uv run ruff format --check .`.

---

## File Structure

**New backend package — `backend/app/auth/`**, because these five concerns change together and none of them belongs to `identity/`, which deliberately knows nothing about HTTP:

| File | Responsibility |
|---|---|
| `auth/__init__.py` | Re-exports `build_oauth`, `PROVIDER_LABELS`, `OAuthProfile`. **Never binds the name `router`** — `main.py` does `from .auth import router as auth_module` and needs that to resolve to the submodule, exactly as `history` does today |
| `auth/providers.py` | Which providers are configured; the Authlib registry; per-provider userinfo normalisation |
| `auth/claim.py` | Signing and verifying the contested-claim token |
| `auth/resolution.py` | The §5.1 decision table, as a pure function over already-fetched facts |
| `auth/router.py` | The six routes; HTTP only, no decisions |

**Modified backend:**

| File | Change |
|---|---|
| `app/config.py` | Six new settings + `configured_providers` |
| `app/errors.py` | Four new `AppError` subclasses |
| `app/db/schema.py` | `oauth_identities` + three `users_profile` columns, for a fresh database |
| `app/db/migrations.py` | The same, as migration 003, for a database that already exists |
| `app/identity/models.py` | `User` gains `email`, `display_name`, `avatar_url` |
| `app/identity/store.py` | `get`/`mint_guest` select the new columns; `promote`, `attach_identity`, `lookup_identity`, `has_activity` |
| `app/deps.py` | `_set_session_cookie` → public `set_session_cookie`; `clear_session_cookie` |
| `app/main.py` | `SessionMiddleware`, `app.state.oauth`, include the auth router |

**Frontend:**

| File | Change |
|---|---|
| `lib/types.ts` | `Session`, `AuthProvider` |
| `lib/api/endpoints.ts` | `fetchSession`, `fetchProviders`, `logout`, `confirmClaim` |
| `store/useSessionStore.ts` | **New.** Session state + `sessionVersion` |
| `components/layout/AccountMenu.tsx` | **New.** Avatar + menu, or Sign in |
| `components/layout/SignInSheet.tsx` | **New.** Provider buttons |
| `components/layout/ClaimConflictDialog.tsx` | **New.** The §5.2 prompt |
| `components/layout/Header.tsx` | Mount `AccountMenu` |
| `app/page.tsx` | Mount the dialog; bump-driven refetch |

---

### Task 1: Configuration, provider registry, and the dependency additions

**Files:**
- Create: `backend/app/auth/__init__.py`, `backend/app/auth/providers.py`
- Modify: `backend/app/config.py`, `backend/app/errors.py`, `backend/pyproject.toml`, `requirements.txt`, `.env.example`
- Test: `backend/tests/auth/__init__.py`, `backend/tests/auth/test_providers.py`

**Interfaces:**
- Consumes: `Settings` (`app/config.py`), `AppError` (`app/errors.py`)
- Produces:
  - `Settings.google_client_id/google_client_secret/github_client_id/github_client_secret/public_base_url/auth_mock`
  - `Settings.configured_providers -> tuple[str, ...]` — ordered `("google", "github")`, filtered to those with both id and secret
  - `app.auth.providers.PROVIDER_LABELS: dict[str, str]`
  - `app.auth.providers.build_oauth(settings: Settings) -> OAuth` — an Authlib registry with only the configured providers registered
  - `AuthProviderUnavailableError`, `AuthStateInvalidError`, `AuthExchangeFailedError`, `ClaimTokenInvalidError`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/auth/test_providers.py
"""Which providers exist, and the rule that keeps the quick start zero-config."""

from __future__ import annotations

import dataclasses

import pytest

from app.auth.providers import PROVIDER_LABELS, build_oauth
from app.config import Settings


def _settings(**overrides) -> Settings:
    return dataclasses.replace(Settings(database_url="postgresql://x/y"), **overrides)


class TestConfiguredProviders:
    def test_none_configured_is_the_default(self):
        """The zero-config quick start: no credentials, no sign-in, guest only."""
        assert _settings().configured_providers == ()

    def test_a_provider_needs_both_halves(self):
        """An id with no secret cannot complete an exchange, so offering the
        button would produce a dead end rather than a sign-in."""
        assert _settings(google_client_id="id").configured_providers == ()
        assert _settings(google_client_secret="secret").configured_providers == ()

    def test_both_halves_configure_it(self):
        settings = _settings(google_client_id="id", google_client_secret="secret")
        assert settings.configured_providers == ("google",)

    def test_order_is_stable(self):
        """The UI renders them in this order; a set would reshuffle the sheet
        between deployments."""
        settings = _settings(
            github_client_id="i", github_client_secret="s",
            google_client_id="i", google_client_secret="s",
        )
        assert settings.configured_providers == ("google", "github")

    @pytest.mark.parametrize("provider", ["google", "github"])
    def test_every_provider_has_a_label(self, provider):
        assert PROVIDER_LABELS[provider]


class TestRegistry:
    def test_only_configured_providers_are_registered(self):
        oauth = build_oauth(_settings(google_client_id="id", google_client_secret="secret"))
        assert oauth.create_client("google") is not None
        assert oauth.create_client("github") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 3: Add the dependency to both requirement files**

`backend/pyproject.toml`, in `[project].dependencies`:

```toml
    "authlib>=1.3.0",
```

`requirements.txt` — the Vercel function's list. It is a deliberate subset, and `test_vercel_requirements.py` enforces that anything imported at module scope appears here:

```
# OAuth client. Imported at module scope by app/auth/providers.py, so the
# function fails to import without it -- the failure mode that took every
# /api/* route down on 2026-08-25.
authlib>=1.3.0
```

Then `cd backend && uv sync`.

- [ ] **Step 4: Add the settings**

In `backend/app/config.py`, inside `class Settings`:

```python
    #: OAuth client credentials. A provider with either half missing is not
    #: offered at all -- see `configured_providers`. Absent entirely is the
    #: default and keeps the quick start zero-config.
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    #: Base URL the browser reaches us on, used to build the OAuth callback.
    #: Empty means "derive it from the request". Set it explicitly wherever a
    #: proxy rewrites the host: a wrong callback URL is rejected by the
    #: provider with an error that names neither the cause nor this setting.
    public_base_url: str = ""

    #: Enables /api/auth/dev-login/{user_id}, which signs a session cookie for
    #: an arbitrary user with no provider involved. E2E only. Refused unless
    #: this is true, because it is an unauthenticated session-forgery route.
    auth_mock: bool = False
```

And the property, after `market_source_name`:

```python
    @property
    def configured_providers(self) -> tuple[str, ...]:
        """Providers with both halves of their credentials, in display order.

        A tuple rather than a set: the sign-in sheet renders them in this
        order, and a set would reshuffle it between deployments.
        """
        pairs = (
            ("google", self.google_client_id, self.google_client_secret),
            ("github", self.github_client_id, self.github_client_secret),
        )
        return tuple(name for name, id_, secret in pairs if id_.strip() and secret.strip())
```

In `from_env`, alongside the existing reads:

```python
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        github_client_id=os.getenv("GITHUB_CLIENT_ID", ""),
        github_client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
        public_base_url=os.getenv("PUBLIC_BASE_URL", ""),
        auth_mock=os.getenv("AUTH_MOCK", "").lower() == "true",
```

- [ ] **Step 5: Add the four error classes**

In `backend/app/errors.py`, after `CleanupForbiddenError`:

```python
class AuthProviderUnavailableError(AppError):
    """A provider that is not configured on this deployment.

    404 rather than 400: the route genuinely does not exist here, and saying
    so lets the frontend hide a button it cannot fulfil rather than render one
    that dead-ends.
    """

    status_code, code = 404, "AUTH_PROVIDER_UNAVAILABLE"


class AuthStateInvalidError(AppError):
    """The callback's state or PKCE verifier did not match the cookie.

    Ordinary rather than sinister: a bookmarked callback URL, a back button,
    or a sign-in begun before a redeploy rotated the secret all land here.
    """

    status_code, code = 400, "AUTH_STATE_INVALID"


class AuthExchangeFailedError(AppError):
    """The provider refused the code exchange or the userinfo request."""

    status_code, code = 502, "AUTH_EXCHANGE_FAILED"


class ClaimTokenInvalidError(AppError):
    """A claim token that is expired, tampered with, or not this session's."""

    status_code, code = 400, "CLAIM_TOKEN_INVALID"
```

- [ ] **Step 6: Write the provider registry**

`backend/app/auth/providers.py`:

```python
"""Which providers this deployment offers, and how to talk to them.

Registering only the configured providers is what makes `oauth.create_client`
return None for the others -- so the router has one place to ask rather than
re-deriving the rule from settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from authlib.integrations.starlette_client import OAuth

from ..config import Settings

#: Display names for the sign-in sheet. Also the set of providers this app
#: knows how to normalise userinfo for -- adding a key here without adding a
#: branch to `normalize_profile` would produce a button that 502s.
PROVIDER_LABELS: dict[str, str] = {"google": "Google", "github": "GitHub"}


@dataclass(frozen=True)
class OAuthProfile:
    """One provider's answer, reduced to what this app stores.

    `subject` is the provider's own immutable id, and the only thing identity
    resolution matches on. Email is carried for display and never for lookup
    (D-6): cross-provider email matching is an account-takeover vector where a
    provider does not guarantee the address is verified.
    """

    provider: str
    subject: str
    email: str | None
    name: str | None
    avatar: str | None


def build_oauth(settings: Settings) -> OAuth:
    """An Authlib registry holding exactly the configured providers."""
    oauth = OAuth()
    configured = settings.configured_providers

    if "google" in configured:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            # S256 is PKCE. Authlib stores the verifier in the Starlette
            # session cookie, which is why SessionMiddleware is mandatory --
            # see main.py.
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )

    if "github" in configured:
        oauth.register(
            name="github",
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            # `user:email` because GitHub omits a private address from /user;
            # without it a user whose email is hidden signs in with no email
            # at all, which is legal here but shows an empty account menu.
            client_kwargs={"scope": "read:user user:email"},
        )

    return oauth
```

`backend/app/auth/__init__.py`:

```python
"""OAuth sign-in: providers, identity resolution, the claim flow, routes."""

from .providers import PROVIDER_LABELS, OAuthProfile, build_oauth

__all__ = ["PROVIDER_LABELS", "OAuthProfile", "build_oauth"]
```

- [ ] **Step 7: Run the tests**

Run: `cd backend && uv run pytest tests/auth/test_providers.py tests/test_vercel_requirements.py -v`
Expected: PASS — including the requirements guard, which now sees `authlib` declared.

- [ ] **Step 8: Document the variables**

Append to `.env.example`, after `SESSION_SECRET`:

```bash
# Optional: OAuth sign-in. Absent, the app is guest-only and no sign-in button
# is rendered -- which is the zero-config quick start. Both halves of a pair
# are required; an id with no secret is treated as unconfigured.
# Callback URL to register with the provider:
#   <your origin>/api/auth/callback/google  (and .../github)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Origin the browser reaches this app on, used to build the callback URL.
# Empty derives it from the request (X-Forwarded-Proto/Host, then the request
# URL). Set it explicitly behind a proxy that rewrites the host.
PUBLIC_BASE_URL=

# E2E only: enables /api/auth/dev-login/{user_id}, which signs a session for
# any user with no provider involved. Never set this in production.
AUTH_MOCK=false
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/auth backend/app/config.py backend/app/errors.py \
        backend/pyproject.toml backend/uv.lock requirements.txt .env.example \
        backend/tests/auth
git commit -m "Add the OAuth provider registry and its configuration"
```

---

### Task 2: Schema and migration for identities

**Files:**
- Modify: `backend/app/db/schema.py`, `backend/app/db/migrations.py`
- Test: `backend/tests/db/test_identity_schema.py`

**Interfaces:**
- Consumes: `Database` (`app/db/connection.py`), `run_migrations`
- Produces: table `oauth_identities (provider, provider_user_id, user_id, email, created_at)` with `PRIMARY KEY (provider, provider_user_id)`, `user_id` FK cascading from `users_profile`; `users_profile.email/display_name/avatar_url`

**Why both files:** `CREATE TABLE IF NOT EXISTS` in `schema.py` serves a database that does not exist yet. It cannot add a column to one Neon already has — that is the gap that bites on the *second* deploy. Every change needs both, and the migration statements must be safe to re-run because there is no version table.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/db/test_identity_schema.py
"""The identity tables, on a fresh database and on one that already exists."""

from __future__ import annotations

import pytest

from app.db import run_migrations


@pytest.mark.asyncio
class TestFreshSchema:
    async def test_oauth_identities_exists(self, db):
        row = await db.fetch_one(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            "WHERE table_name = 'oauth_identities'"
        )
        assert row["n"] == 1

    @pytest.mark.parametrize("column", ["email", "display_name", "avatar_url"])
    async def test_users_profile_carries_the_identity_columns(self, db, column):
        row = await db.fetch_one(
            "SELECT COUNT(*) AS n FROM information_schema.columns "
            "WHERE table_name = 'users_profile' AND column_name = $1",
            column,
        )
        assert row["n"] == 1


@pytest.mark.asyncio
class TestConstraints:
    async def test_one_identity_per_provider_subject(self, db, seeded_user_id):
        await db.execute(
            "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
            "created_at) VALUES ('google', 'sub-1', $1, 'a@b.c', '2026-01-01T00:00:00Z')",
            seeded_user_id,
        )
        with pytest.raises(Exception):
            await db.execute(
                "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
                "created_at) VALUES ('google', 'sub-1', $1, 'a@b.c', '2026-01-01T00:00:00Z')",
                seeded_user_id,
            )

    async def test_deleting_the_user_removes_the_identity(self, db, seeded_user_id):
        """Guest expiry is a single DELETE; an orphaned identity would let a
        deleted account be signed back into."""
        await db.execute(
            "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
            "created_at) VALUES ('github', 'sub-2', $1, NULL, '2026-01-01T00:00:00Z')",
            seeded_user_id,
        )
        await db.execute("DELETE FROM users_profile WHERE id = $1", seeded_user_id)
        row = await db.fetch_one("SELECT COUNT(*) AS n FROM oauth_identities")
        assert row["n"] == 0


@pytest.mark.asyncio
async def test_migrations_are_idempotent(db):
    """No version table records what has run, so every statement must survive
    a second execution -- which is what happens on every single startup."""
    await run_migrations(db)
    await run_migrations(db)
```

Add to `backend/tests/conftest.py`, beside the existing fixtures:

```python
@pytest_asyncio.fixture
async def seeded_user_id(db) -> str:
    """A real users_profile row, for tests that need a foreign key to satisfy."""
    from app.db import seed_user

    await seed_user(db, TEST_USER_ID, utcnow_iso())
    return TEST_USER_ID
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/db/test_identity_schema.py -v`
Expected: FAIL — `test_oauth_identities_exists` asserts `0 == 1`

- [ ] **Step 3: Add the table to the fresh-database schema**

In `backend/app/db/schema.py`, extend the `users_profile` definition and append the new table:

```sql
CREATE TABLE IF NOT EXISTS users_profile (
    id           TEXT PRIMARY KEY,
    cash_balance DOUBLE PRECISION NOT NULL,
    created_at   TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'guest' CHECK (kind IN ('guest','user')),
    last_seen_at TEXT NOT NULL DEFAULT '',
    email        TEXT,
    display_name TEXT,
    avatar_url   TEXT
);

CREATE TABLE IF NOT EXISTS oauth_identities (
    provider         TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    user_id          TEXT NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
    email            TEXT,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (provider, provider_user_id)
);

CREATE INDEX IF NOT EXISTS idx_oauth_user ON oauth_identities (user_id);
```

- [ ] **Step 4: Add migration 003**

Append to `MIGRATIONS` in `backend/app/db/migrations.py`. Never edit an existing entry — the list is append-only:

```python
    # 003 -- identity. The profile columns are display data only; nothing
    # resolves an account by email (D-6). oauth_identities is created here as
    # well as in schema.py because Neon already has the database, so
    # schema.py's CREATE TABLE IF NOT EXISTS never runs against it.
    "ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS email TEXT",
    "ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS display_name TEXT",
    "ALTER TABLE users_profile ADD COLUMN IF NOT EXISTS avatar_url TEXT",
    """
    CREATE TABLE IF NOT EXISTS oauth_identities (
        provider         TEXT NOT NULL,
        provider_user_id TEXT NOT NULL,
        user_id          TEXT NOT NULL REFERENCES users_profile (id) ON DELETE CASCADE,
        email            TEXT,
        created_at       TEXT NOT NULL,
        PRIMARY KEY (provider, provider_user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_oauth_user ON oauth_identities (user_id)",
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/db/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/db/schema.py backend/app/db/migrations.py \
        backend/tests/db/test_identity_schema.py backend/tests/conftest.py
git commit -m "Add oauth_identities and the profile columns"
```

---

### Task 3: The identity store — lookup, link, promote, and the activity probe

**Files:**
- Modify: `backend/app/identity/models.py`, `backend/app/identity/store.py`, `backend/app/identity/__init__.py`
- Test: `backend/tests/identity/test_identity_store.py`

**Interfaces:**
- Consumes: `Database`, `Settings`, `UserStore.mint_guest()`, `seed_user`
- Produces, on `UserStore`:
  - `async def lookup_identity(provider: str, subject: str) -> str | None` — the `user_id`, or None
  - `async def attach_identity(user_id: str, provider: str, subject: str, email: str | None) -> None`
  - `async def promote(user_id: str, email: str | None, name: str | None, avatar: str | None) -> User` — sets `kind='user'` and the profile columns, returns the reloaded row
  - `async def has_activity(user_id: str) -> bool`
  - `User` gains `email: str | None`, `display_name: str | None`, `avatar_url: str | None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/identity/test_identity_store.py
"""Attaching a provider identity to a row, and asking whether it has been used."""

from __future__ import annotations

import pytest

from app.identity import UserStore


@pytest.fixture
def store(db, settings) -> UserStore:
    return UserStore(db, settings)


@pytest.mark.asyncio
class TestLookup:
    async def test_an_unknown_identity_is_none(self, store):
        assert await store.lookup_identity("google", "nobody") is None

    async def test_a_linked_identity_returns_its_user(self, store):
        user = await store.mint_guest()
        await store.attach_identity(user.id, "google", "sub-1", "a@b.c")
        assert await store.lookup_identity("google", "sub-1") == user.id

    async def test_the_same_subject_at_another_provider_is_a_different_identity(self, store):
        """D-6 in the schema: the key is the pair, never the email or the
        subject alone. GitHub's user 12345 is not Google's user 12345."""
        user = await store.mint_guest()
        await store.attach_identity(user.id, "google", "12345", None)
        assert await store.lookup_identity("github", "12345") is None


@pytest.mark.asyncio
class TestPromote:
    async def test_promotion_is_in_place(self, store):
        """The row keeps its id, so the cookie already in the browser stays
        valid and every row that points at it follows the user across."""
        guest = await store.mint_guest()
        promoted = await store.promote(guest.id, "a@b.c", "Ada", "https://img/x.png")
        assert promoted.id == guest.id
        assert promoted.kind == "user"
        assert (promoted.email, promoted.display_name, promoted.avatar_url) == (
            "a@b.c", "Ada", "https://img/x.png",
        )

    async def test_promotion_keeps_the_portfolio(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "UPDATE users_profile SET cash_balance = 4242.0 WHERE id = $1", guest.id
        )
        promoted = await store.promote(guest.id, None, None, None)
        assert promoted.cash_balance == 4242.0


@pytest.mark.asyncio
class TestHasActivity:
    async def test_a_freshly_minted_guest_has_none(self, store):
        """The common case, and the one that must never produce a prompt: an
        untouched guest signing in has nothing to lose."""
        guest = await store.mint_guest()
        assert await store.has_activity(guest.id) is False

    async def test_a_trade_is_activity(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES ('t1', $1, 'AAPL', 'buy', 1, 190.0, '2026-01-01T00:00:00Z')",
            guest.id,
        )
        assert await store.has_activity(guest.id) is True

    async def test_a_chat_message_is_activity(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES ('c1', $1, 'user', 'hi', NULL, '2026-01-01T00:00:00Z')",
            guest.id,
        )
        assert await store.has_activity(guest.id) is True

    async def test_removing_a_seeded_ticker_is_activity(self, store, db):
        """Activity is a change away from the seed, in either direction --
        counting only additions would discard a curated watchlist silently."""
        guest = await store.mint_guest()
        await db.execute(
            "DELETE FROM watchlist WHERE user_id = $1 AND ticker = 'NFLX'", guest.id
        )
        assert await store.has_activity(guest.id) is True

    async def test_adding_a_ticker_is_activity(self, store, db):
        guest = await store.mint_guest()
        await db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) "
            "VALUES ('w1', $1, 'PYPL', '2026-01-01T00:00:00Z')",
            guest.id,
        )
        assert await store.has_activity(guest.id) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/identity/test_identity_store.py -v`
Expected: FAIL — `AttributeError: 'UserStore' object has no attribute 'lookup_identity'`

- [ ] **Step 3: Widen the User record**

In `backend/app/identity/models.py`:

```python
@dataclass(frozen=True)
class User:
    """One row of users_profile.

    `kind` distinguishes a guest from a signed-in user. It is read from the
    row on every request rather than carried in the cookie, so promoting a
    guest in place takes effect immediately.

    The three profile fields are display data, populated at sign-in. They are
    never used to resolve an identity (D-6) -- `oauth_identities` is the only
    thing that does that.
    """

    id: str
    cash_balance: float
    kind: str
    created_at: str
    last_seen_at: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
```

Update `_to_user` in `store.py` to read them, and every `SELECT` in that module to list the new columns.

- [ ] **Step 4: Implement the four methods**

Append to `UserStore` in `backend/app/identity/store.py`:

```python
    async def lookup_identity(self, provider: str, subject: str) -> str | None:
        """The user a provider identity belongs to, or None if it is new.

        The pair is the whole key. Matching on email instead -- or as a
        fallback -- is an account-takeover vector wherever a provider does not
        guarantee the address is verified (D-6).
        """
        row = await self._db.fetch_one(
            "SELECT user_id FROM oauth_identities WHERE provider = ? AND provider_user_id = ?",
            provider,
            subject,
        )
        return row["user_id"] if row else None

    async def attach_identity(
        self, user_id: str, provider: str, subject: str, email: str | None
    ) -> None:
        """Link a provider identity to a row.

        ON CONFLICT DO NOTHING rather than an upsert: the pair is already the
        primary key, so a conflict means this identity is linked, and the only
        row it could be linked to is the one the caller just resolved.
        """
        await self._db.execute(
            "INSERT INTO oauth_identities (provider, provider_user_id, user_id, email, "
            "created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (provider, provider_user_id) DO NOTHING",
            provider,
            subject,
            user_id,
            email,
            utcnow_iso(),
        )

    async def promote(
        self, user_id: str, email: str | None, name: str | None, avatar: str | None
    ) -> User:
        """Turn a guest row into a signed-in user, in place.

        In place is the whole point: the id does not change, so the cookie
        already in the browser stays valid and every watchlist row, position,
        trade and message follows the user across without being touched.

        COALESCE keeps a previously stored value when a provider returns null
        for a field -- signing in with GitHub after Google should not blank an
        avatar GitHub happens not to expose.
        """
        await self._db.execute(
            "UPDATE users_profile SET kind = 'user', email = COALESCE(?, email), "
            "display_name = COALESCE(?, display_name), avatar_url = COALESCE(?, avatar_url) "
            "WHERE id = ?",
            email,
            name,
            avatar,
            user_id,
        )
        user = await self.get(user_id)
        if user is None:  # pragma: no cover -- the caller just resolved this row
            raise LookupError(f"Promoted a user that does not exist: {user_id}")
        return user

    async def has_activity(self, user_id: str) -> bool:
        """Whether this user has done anything worth warning about losing.

        Three signals, per the spec: any trade, any chat message, or a
        watchlist that differs from the seeded ten. The watchlist is compared
        by count *and* by membership, because a removal followed by an
        addition leaves the count untouched while the list is no longer the
        one we seeded.

        The common case is an untouched guest, which must not produce a
        prompt -- a warning that fires on every sign-in trains people to
        dismiss it, and the one time it matters they will.
        """
        row = await self._db.fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM trades WHERE user_id = ?)        AS trades,
                (SELECT COUNT(*) FROM chat_messages WHERE user_id = ?) AS messages,
                (SELECT COUNT(*) FROM watchlist WHERE user_id = ?)     AS watched,
                (SELECT COUNT(*) FROM watchlist WHERE user_id = ? AND ticker <> ALL(?))
                                                                       AS unseeded
            """,
            user_id,
            user_id,
            user_id,
            user_id,
            list(DEFAULT_TICKERS),
        )
        if row is None:  # pragma: no cover
            return False
        return bool(
            row["trades"]
            or row["messages"]
            or row["unseeded"]
            or row["watched"] != len(DEFAULT_TICKERS)
        )
```

Import `DEFAULT_TICKERS` from `..market.tickers` at the top of `store.py` (it is what `seed_user` already seeds).

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/identity/ -v`
Expected: PASS

- [ ] **Step 6: Run the whole suite — `User` grew three fields**

Run: `cd backend && uv run pytest -q`
Expected: PASS. If a test constructs `User(...)` positionally it still works, because the new fields default to None.

- [ ] **Step 7: Commit**

```bash
git add backend/app/identity backend/tests/identity/test_identity_store.py
git commit -m "Link provider identities to a user, and ask whether a guest has been used"
```

---

### Task 4: Identity resolution as a pure decision

**Files:**
- Create: `backend/app/auth/resolution.py`
- Test: `backend/tests/auth/test_resolution.py`

**Interfaces:**
- Consumes: nothing at runtime — this module imports no database and no HTTP
- Produces:
  - `class Outcome(StrEnum): PROMOTE, SWITCH, CREATE, CONFLICT`
  - `class Decision(NamedTuple): outcome: Outcome; target_user_id: str | None`
  - `def decide(*, linked_user_id: str | None, session_user_id: str | None, session_kind: str | None, session_has_activity: bool) -> Decision`

**Why a pure function:** the §5.1 matrix is the part of this feature that is easy to get subtly wrong and expensive to test through HTTP. Separating it means the whole matrix is covered by tests that need no database, no provider, and no browser — and the router keeps no branching of its own.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/auth/test_resolution.py
"""The §5.1 matrix, in full. No database, no provider, no HTTP."""

from __future__ import annotations

from app.auth.resolution import Outcome, decide


class TestKnownIdentity:
    """The identity has signed in before, so an account already exists (D-2:
    it wins)."""

    def test_an_untouched_guest_is_switched_silently(self):
        decision = decide(
            linked_user_id="user-1",
            session_user_id="guest-9",
            session_kind="guest",
            session_has_activity=False,
        )
        assert decision == (Outcome.SWITCH, "user-1")

    def test_a_used_guest_produces_a_conflict(self):
        """The only case that cannot be decided server-side: real activity is
        about to be discarded, so the user is asked first."""
        decision = decide(
            linked_user_id="user-1",
            session_user_id="guest-9",
            session_kind="guest",
            session_has_activity=True,
        )
        assert decision == (Outcome.CONFLICT, "user-1")

    def test_signing_in_as_yourself_is_never_a_conflict(self):
        """Re-authenticating an account you are already in must not warn about
        discarding that account's own activity."""
        decision = decide(
            linked_user_id="user-1",
            session_user_id="user-1",
            session_kind="user",
            session_has_activity=True,
        )
        assert decision == (Outcome.SWITCH, "user-1")

    def test_a_signed_in_user_switching_accounts_is_not_asked(self):
        """Their activity is safe in the account they are leaving -- nothing
        is discarded, so there is nothing to confirm."""
        decision = decide(
            linked_user_id="user-1",
            session_user_id="user-2",
            session_kind="user",
            session_has_activity=True,
        )
        assert decision == (Outcome.SWITCH, "user-1")

    def test_no_session_at_all_is_a_switch(self):
        decision = decide(
            linked_user_id="user-1",
            session_user_id=None,
            session_kind=None,
            session_has_activity=False,
        )
        assert decision == (Outcome.SWITCH, "user-1")


class TestNewIdentity:
    """First time this provider identity has been seen."""

    def test_a_guest_is_promoted_in_place(self):
        """Activity is irrelevant here -- promotion keeps every row, so there
        is nothing to lose and nothing to ask about."""
        for has_activity in (True, False):
            decision = decide(
                linked_user_id=None,
                session_user_id="guest-9",
                session_kind="guest",
                session_has_activity=has_activity,
            )
            assert decision == (Outcome.PROMOTE, "guest-9")

    def test_a_signed_in_user_gets_a_second_identity_on_the_same_row(self):
        """Signing in with GitHub while already signed in with Google links
        both to one account rather than stranding the portfolio."""
        decision = decide(
            linked_user_id=None,
            session_user_id="user-1",
            session_kind="user",
            session_has_activity=True,
        )
        assert decision == (Outcome.PROMOTE, "user-1")

    def test_no_session_creates_a_user(self):
        decision = decide(
            linked_user_id=None,
            session_user_id=None,
            session_kind=None,
            session_has_activity=False,
        )
        assert decision == (Outcome.CREATE, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_resolution.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.resolution'`

- [ ] **Step 3: Implement**

```python
# backend/app/auth/resolution.py
"""The sign-in decision, as a function of facts already gathered.

Kept free of I/O on purpose: this matrix is the part of sign-in that is
easiest to get subtly wrong, and a pure function makes every branch testable
without a database, a provider, or a browser. The router gathers the facts and
carries out the verdict; it holds no branching of its own.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class Outcome(StrEnum):
    #: Attach this identity to the session's row and mark it a user. The id
    #: does not change, so the portfolio comes along.
    PROMOTE = "promote"
    #: Point the cookie at an existing account. The session's own row is left
    #: alone -- an untouched guest, which expires on its own.
    SWITCH = "switch"
    #: No session to build on: create a seeded row and link the identity.
    CREATE = "create"
    #: Would discard real activity. Ask first (§5.2).
    CONFLICT = "conflict"


class Decision(NamedTuple):
    """The verdict, as a pair.

    A NamedTuple rather than a dataclass so it compares equal to a plain
    tuple: every test in this module states its expectation as
    `(outcome, target)`, and a frozen dataclass would quietly fail all of
    them by returning NotImplemented against a tuple.
    """

    outcome: Outcome
    #: The row to end up in. None only for CREATE, which has none yet.
    target_user_id: str | None


def decide(
    *,
    linked_user_id: str | None,
    session_user_id: str | None,
    session_kind: str | None,
    session_has_activity: bool,
) -> Decision:
    """Resolve a completed OAuth callback to one of four actions.

    `linked_user_id` is the account this provider identity already belongs to,
    or None if it is new. The session arguments describe whoever is holding
    the cookie right now, which may be nobody.
    """
    if linked_user_id is None:
        # A new identity never displaces anything: either it joins the row the
        # caller is already in -- promoting a guest, or adding a second
        # provider to a user -- or there is no row and we make one.
        if session_user_id is not None:
            return Decision(Outcome.PROMOTE, session_user_id)
        return Decision(Outcome.CREATE, None)

    # The identity is known, so that account wins (D-2). The only question is
    # whether anything is lost by leaving the current session behind.
    losing_something = (
        session_kind == "guest"
        and session_has_activity
        and session_user_id != linked_user_id
    )
    if losing_something:
        return Decision(Outcome.CONFLICT, linked_user_id)
    return Decision(Outcome.SWITCH, linked_user_id)
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/auth/test_resolution.py -v`
Expected: PASS — 8 tests

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/resolution.py backend/tests/auth/test_resolution.py
git commit -m "Decide sign-in outcomes without touching the database"
```

---

### Task 5: The claim token

**Files:**
- Create: `backend/app/auth/claim.py`
- Test: `backend/tests/auth/test_claim_token.py`

**Interfaces:**
- Consumes: `itsdangerous` (already a dependency), `Settings.session_secret`
- Produces: `class ClaimToken` with `__init__(secret: str)`, `sign(guest_id: str, target_id: str) -> str`, `verify(raw: str | None, guest_id: str) -> str | None` (returns the target id, or None), and `CLAIM_MAX_AGE = 600`

**The security property this task exists for:** the token is bound to the guest session that produced it. Without that binding, a token leaked through the URL bar, a referrer header, or a shared screenshot lets *anyone* switch their cookie to the target account — the token would be a bearer credential for someone else's portfolio.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/auth/test_claim_token.py
"""The token that carries a contested sign-in across the redirect."""

from __future__ import annotations

import pytest

from app.auth.claim import CLAIM_MAX_AGE, ClaimToken


@pytest.fixture
def token() -> ClaimToken:
    return ClaimToken("secret-for-tests")


class TestRoundTrip:
    def test_a_token_verifies_for_the_guest_that_produced_it(self, token):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw, "guest-1") == "user-9"


class TestRejection:
    def test_another_session_cannot_use_it(self, token):
        """The token travels in a URL -- a referrer, a screenshot, a shared
        link. Bound to its guest, a leaked one is useless to anyone else;
        unbound, it is a bearer credential for someone else's portfolio."""
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw, "guest-2") is None

    def test_a_tampered_token_is_rejected(self, token):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw[:-1] + ("A" if raw[-1] != "A" else "B"), "guest-1") is None

    def test_another_secret_cannot_mint_one(self, token):
        forged = ClaimToken("a-different-secret").sign("guest-1", "user-9")
        assert token.verify(forged, "guest-1") is None

    def test_an_expired_token_is_rejected(self, token):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw, "guest-1", max_age=-1) is None

    @pytest.mark.parametrize("raw", [None, "", "not-a-token"])
    def test_junk_is_rejected_without_raising(self, raw, token):
        assert token.verify(raw, "guest-1") is None


def test_the_window_is_short():
    """Long enough to read a dialog, short enough that a token left in
    somebody's history is inert by the time it is found."""
    assert CLAIM_MAX_AGE == 600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_claim_token.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.claim'`

- [ ] **Step 3: Implement**

```python
# backend/app/auth/claim.py
"""The short-lived token that carries a contested sign-in across a redirect.

The callback cannot switch the cookie -- doing so would discard a guest's
work without asking -- so it hands the browser a token naming the account it
declined to switch to, and `POST /api/auth/claim` completes the switch once
the user confirms.

The token is bound to the guest session that produced it. It travels in a URL,
which means it can end up in a referrer header, a screenshot, or a pasted
link; bound, a leaked token does nothing for whoever finds it, because their
own session id will not match. Unbound it would be a bearer credential for
someone else's portfolio.
"""

from __future__ import annotations

import logging

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

#: Ten minutes: long enough to read the dialog and decide, short enough that a
#: token left in a browser history is inert by the time anyone finds it.
CLAIM_MAX_AGE = 600

_SALT = "trader-claim-v1"


class ClaimToken:
    """Signs the pair (guest that asked, account it wants) and reads it back."""

    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)

    def sign(self, guest_id: str, target_id: str) -> str:
        return self._serializer.dumps({"gid": guest_id, "tid": target_id})

    def verify(self, raw: str | None, guest_id: str, max_age: int = CLAIM_MAX_AGE) -> str | None:
        """The account to switch to, or None for anything not usable.

        Every rejection returns None rather than raising: the caller turns
        that into one `CLAIM_TOKEN_INVALID`, and distinguishing "expired" from
        "not yours" in the response would tell a prober which it was.
        """
        if not raw:
            return None
        try:
            # SignatureExpired before BadData: it is a subclass of
            # BadSignature, itself a subclass of BadData, so a narrower branch
            # below would never fire.
            payload = self._serializer.loads(raw, max_age=max_age)
        except SignatureExpired:
            return None
        except BadData:
            logger.warning("Rejected a claim token with a bad signature or payload")
            return None
        if not isinstance(payload, dict) or payload.get("gid") != guest_id:
            return None
        target = payload.get("tid")
        return target if isinstance(target, str) and target else None
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/auth/test_claim_token.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/claim.py backend/tests/auth/test_claim_token.py
git commit -m "Bind the claim token to the session that produced it"
```

---

### Task 6: The auth routes

**Files:**
- Create: `backend/app/auth/router.py`
- Modify: `backend/app/deps.py`, `backend/app/main.py`
- Test: `backend/tests/auth/test_auth_routes.py`

**Interfaces:**
- Consumes: `build_oauth`, `OAuthProfile`, `PROVIDER_LABELS`, `decide`, `Outcome`, `ClaimToken`, `UserStore`, `SessionCookie`, the four new errors
- Produces:
  - `router` with `GET /api/auth/providers`, `GET /api/auth/login/{provider}`, `GET /api/auth/callback/{provider}`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/claim`
  - `app.deps.set_session_cookie(request, response, cookie, user_id)` — the existing private helper, made public
  - `app.deps.clear_session_cookie(response)`
  - `app.state.oauth`, `app.state.claim_token`

**The trap this task must avoid:** `get_current_user` re-issues the session cookie on *every* response. A callback route that also depended on it would emit two `Set-Cookie: trader_session=` headers — the dependency's, naming the old user, and the route's, naming the new one — and which wins is left to the browser. So the auth routes resolve the session themselves, from the cookie, without the auto-minting dependency, and set the cookie exactly once on a response they build.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/auth/test_auth_routes.py
"""The six routes, against a real app with a mock provider."""

from __future__ import annotations

import dataclasses

import pytest

from app.auth.providers import OAuthProfile
from app.identity import COOKIE_NAME

from tests.conftest import CLIENT_BASE_URL


@pytest.fixture
def configured_settings(settings):
    return dataclasses.replace(
        settings, google_client_id="id", google_client_secret="secret"
    )


@pytest.fixture
def auth_client(configured_settings, monkeypatch):
    """A client whose provider exchange is stubbed at the seam.

    Only `_complete_exchange` is replaced -- everything below it (the decision,
    the store writes, the cookie) is the real code path. Stubbing at the route
    level instead would test the mock.
    """
    from fastapi.testclient import TestClient

    from app.auth import router as router_module
    from app.main import create_app

    profile = OAuthProfile(
        provider="google", subject="sub-1", email="a@b.c", name="Ada", avatar=None
    )

    async def fake_exchange(request, provider):
        return dataclasses.replace(profile, provider=provider, subject=request.query_params["sub"])

    monkeypatch.setattr(router_module, "_complete_exchange", fake_exchange)
    with TestClient(create_app(configured_settings), base_url=CLIENT_BASE_URL) as client:
        yield client


class TestProviders:
    def test_lists_only_what_is_configured(self, auth_client):
        body = auth_client.get("/api/auth/providers").json()
        assert body == {"providers": [{"name": "google", "label": "Google"}]}

    def test_an_unconfigured_deployment_lists_none(self, api_client):
        assert api_client.get("/api/auth/providers").json() == {"providers": []}

    def test_login_for_an_unconfigured_provider_is_404(self, api_client):
        response = api_client.get("/api/auth/login/google", follow_redirects=False)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"


class TestMe:
    def test_a_first_visit_is_a_guest(self, api_client):
        body = api_client.get("/api/auth/me").json()
        assert body["kind"] == "guest"
        assert body["email"] is None
        assert body["hasActivity"] is False

    def test_it_mints_a_session(self, api_client):
        """/api/auth/me is an ordinary user-resolving route -- the frontend
        calls it on mount, and that call is what gives a first-time visitor
        their guest."""
        assert api_client.get("/api/auth/me").status_code == 200
        assert COOKIE_NAME in api_client.cookies


class TestCallback:
    def test_a_new_identity_promotes_the_guest_in_place(self, auth_client):
        before = auth_client.get("/api/auth/me").json()
        response = auth_client.get(
            "/api/auth/callback/google?sub=sub-1", follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"] == "/"
        after = auth_client.get("/api/auth/me").json()
        assert after["id"] == before["id"]
        assert after["kind"] == "user"
        assert after["email"] == "a@b.c"

    def test_signing_in_again_from_a_clean_guest_switches_silently(self, auth_client):
        auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        signed_in = auth_client.get("/api/auth/me").json()

        auth_client.post("/api/auth/logout")
        fresh_guest = auth_client.get("/api/auth/me").json()
        assert fresh_guest["id"] != signed_in["id"]

        auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        assert auth_client.get("/api/auth/me").json()["id"] == signed_in["id"]

    def test_a_used_guest_is_asked_before_being_discarded(self, auth_client):
        auth_client.get("/api/auth/callback/google?sub=sub-1", follow_redirects=False)
        signed_in = auth_client.get("/api/auth/me").json()
        auth_client.post("/api/auth/logout")

        auth_client.post("/api/watchlist", json={"ticker": "PYPL"})
        contested = auth_client.get("/api/auth/me").json()

        response = auth_client.get(
            "/api/auth/callback/google?sub=sub-1", follow_redirects=False
        )
        assert response.status_code == 307
        assert response.headers["location"].startswith("/?claim=conflict&token=")
        # The cookie is untouched until the user confirms.
        assert auth_client.get("/api/auth/me").json()["id"] == contested["id"]

        token = response.headers["location"].split("token=")[1]
        assert auth_client.post("/api/auth/claim", json={"token": token}).status_code == 200
        assert auth_client.get("/api/auth/me").json()["id"] == signed_in["id"]


class TestClaimRejection:
    def test_a_token_from_another_session_is_refused(self, auth_client, configured_settings):
        from app.auth.claim import ClaimToken

        forged = ClaimToken(configured_settings.session_secret).sign("someone-else", "user-9")
        response = auth_client.post("/api/auth/claim", json={"token": forged})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CLAIM_TOKEN_INVALID"


class TestLogout:
    def test_the_next_request_is_a_fresh_guest(self, api_client):
        first = api_client.get("/api/auth/me").json()["id"]
        api_client.post("/api/auth/logout")
        assert api_client.get("/api/auth/me").json()["id"] != first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_auth_routes.py -v`
Expected: FAIL — 404 on every auth path, because no router is mounted

- [ ] **Step 3: Make the cookie helpers public**

In `backend/app/deps.py`, rename `_set_session_cookie` to `set_session_cookie` (update its two call sites in that file) and add:

```python
def clear_session_cookie(response: Response) -> None:
    """Drop the session. The next request mints a fresh guest.

    The attributes must match the ones the cookie was written with -- a
    browser matches a deletion on name, path and domain, and a `delete_cookie`
    that disagrees on path leaves the original in place while looking like it
    worked.

    There is no server-side revocation to pair this with: the cookie is
    stateless by design, so a copy captured earlier stays valid until it
    expires. Accepted in the spec's session contract, and the reason
    "sign out everywhere" is not offered.
    """
    response.delete_cookie(key=COOKIE_NAME, path="/", httponly=True, samesite="lax")
```

- [ ] **Step 4: Write the router**

```python
# backend/app/auth/router.py
"""Sign-in routes.

HTTP only: the decision lives in `resolution.py` and the writes live in
`UserStore`. What is here is gathering facts, carrying out a verdict, and
setting exactly one cookie.

None of these routes uses `CurrentUserDep` except `/me`. That dependency mints
a guest for any caller without one and re-issues the session cookie on every
response -- so a callback that depended on it would emit two `Set-Cookie:
trader_session` headers, one naming the old user and one the new, and leave
the browser to pick. These routes read the cookie themselves and write it
once, on the response they return.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..deps import CurrentUserDep, clear_session_cookie, set_session_cookie
from ..errors import (
    AuthExchangeFailedError,
    AuthProviderUnavailableError,
    AuthStateInvalidError,
    ClaimTokenInvalidError,
)
from ..identity import COOKIE_NAME, User
from .claim import ClaimToken
from .providers import PROVIDER_LABELS, OAuthProfile
from .resolution import Outcome, decide

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ClaimRequest(BaseModel):
    token: str


def _client(request: Request, provider: str):
    """The Authlib client for a provider, or 404 if this deployment has none."""
    client = request.app.state.oauth.create_client(provider)
    if client is None or provider not in PROVIDER_LABELS:
        raise AuthProviderUnavailableError(f"{provider} sign-in is not configured here.")
    return client


async def _session_user(request: Request) -> User | None:
    """Whoever holds the cookie right now, without minting anybody.

    Deliberately not `get_current_user`: arriving at a callback with no
    session is normal (a cookie-less browser, or one that cleared it
    mid-flow), and minting a guest to immediately discard it would write
    twelve rows per sign-in.
    """
    user_id = request.app.state.session_cookie.verify(request.cookies.get(COOKIE_NAME))
    if not user_id:
        return None
    return await request.app.state.user_store.get(user_id)


def _callback_url(request: Request, provider: str) -> str:
    """Where the provider should send the browser back.

    `PUBLIC_BASE_URL` wins when set, because a proxy that rewrites the host
    makes `request.url_for` produce an origin the provider will reject -- and
    the resulting error names neither the cause nor this setting.
    """
    configured = request.app.state.settings.public_base_url.strip().rstrip("/")
    if configured:
        return f"{configured}/api/auth/callback/{provider}"
    return str(request.url_for("oauth_callback", provider=provider))


async def _complete_exchange(request: Request, provider: str) -> OAuthProfile:
    """Trade the code for a token and reduce the provider's answer to a profile.

    Replaced wholesale in tests: everything below it -- the decision, the
    store writes, the cookie -- is exercised for real, and only the network
    call to a third party is stubbed.
    """
    client = _client(request, provider)
    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        # Authlib raises the same class for a mismatched state and a refused
        # exchange; the message distinguishes them, the type does not. State
        # problems are ordinary (a bookmarked callback, a back button, a
        # redeploy that rotated the secret) and must not read as an outage.
        if "state" in str(exc).lower():
            logger.info("Rejected an OAuth callback with bad state: %s", exc)
            raise AuthStateInvalidError(
                "That sign-in link has expired. Please try again."
            ) from exc
        logger.warning("OAuth exchange failed for %s: %s", provider, exc)
        raise AuthExchangeFailedError(f"{provider} did not complete the sign-in.") from exc

    if provider == "google":
        info = token.get("userinfo") or await client.userinfo(token=token)
        return OAuthProfile(
            provider="google",
            subject=str(info["sub"]),
            email=info.get("email"),
            name=info.get("name"),
            avatar=info.get("picture"),
        )

    # GitHub: no id_token, and /user omits a private address, so the verified
    # primary comes from a second call. A user with no public and no verified
    # address signs in fine and simply has no email.
    profile_response = await client.get("user", token=token)
    profile_response.raise_for_status()
    info = profile_response.json()
    email = info.get("email")
    if not email:
        emails_response = await client.get("user/emails", token=token)
        if emails_response.status_code == 200:
            email = next(
                (
                    entry["email"]
                    for entry in emails_response.json()
                    if entry.get("primary") and entry.get("verified")
                ),
                None,
            )
    return OAuthProfile(
        provider="github",
        subject=str(info["id"]),
        email=email,
        name=info.get("name") or info.get("login"),
        avatar=info.get("avatar_url"),
    )


@router.get("/providers")
async def providers(request: Request) -> dict:
    """What this deployment can offer, so the UI hides what it cannot."""
    configured = request.app.state.settings.configured_providers
    return {
        "providers": [{"name": name, "label": PROVIDER_LABELS[name]} for name in configured]
    }


@router.get("/login/{provider}")
async def login(request: Request, provider: str):
    """Send the browser to the provider.

    A full-page navigation rather than a popup: that is what lets sign-in work
    from a static export with no Node runtime and no `postMessage` channel.
    """
    client = _client(request, provider)
    return await client.authorize_redirect(request, _callback_url(request, provider))


@router.get("/callback/{provider}", name="oauth_callback")
async def oauth_callback(request: Request, provider: str):
    """Complete the exchange and act on the §5.1 decision."""
    profile = await _complete_exchange(request, provider)
    store = request.app.state.user_store

    session = await _session_user(request)
    linked = await store.lookup_identity(profile.provider, profile.subject)
    decision = decide(
        linked_user_id=linked,
        session_user_id=session.id if session else None,
        session_kind=session.kind if session else None,
        session_has_activity=(
            await store.has_activity(session.id)
            if session is not None and session.kind == "guest"
            else False
        ),
    )

    if decision.outcome is Outcome.CONFLICT:
        # Deliberately no cookie on this response: the guest keeps their
        # session until they say otherwise, and cancelling costs them nothing.
        token = request.app.state.claim_token.sign(session.id, decision.target_user_id)
        return RedirectResponse(f"/?claim=conflict&token={token}", status_code=307)

    if decision.outcome is Outcome.CREATE:
        target = await store.mint_guest()
        target_id = target.id
    else:
        target_id = decision.target_user_id

    if decision.outcome in (Outcome.PROMOTE, Outcome.CREATE):
        await store.promote(target_id, profile.email, profile.name, profile.avatar)
        await store.attach_identity(target_id, profile.provider, profile.subject, profile.email)

    response = RedirectResponse("/", status_code=307)
    set_session_cookie(request, response, request.app.state.session_cookie, target_id)
    return response


@router.get("/me")
async def me(user: CurrentUserDep, request: Request) -> dict:
    """Who the caller is. Mints a guest when there is none, like every other
    user-resolving route -- this is the call the frontend makes on mount, so
    it is where a first-time visitor's account comes from."""
    return {
        "id": user.id,
        "kind": user.kind,
        "email": user.email,
        "name": user.display_name,
        "avatar": user.avatar_url,
        "hasActivity": await request.app.state.user_store.has_activity(user.id),
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Drop the session cookie. The next request mints a fresh guest."""
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/claim")
async def claim(body: ClaimRequest, request: Request) -> Response:
    """Complete a contested sign-in the user has confirmed (§5.2)."""
    session = await _session_user(request)
    if session is None:
        raise ClaimTokenInvalidError("That confirmation is no longer valid.")

    target_id = request.app.state.claim_token.verify(body.token, session.id)
    if target_id is None:
        raise ClaimTokenInvalidError("That confirmation is no longer valid.")

    response = Response(status_code=200)
    set_session_cookie(request, response, request.app.state.session_cookie, target_id)
    return response
```

- [ ] **Step 5: Wire it into the app**

In `backend/app/main.py`, inside `create_app`, before the routers:

```python
    # Authlib parks the PKCE verifier and the state here. It must be a cookie
    # rather than process memory: serverless instances share nothing, so an
    # in-memory store fails intermittently and unreproducibly -- the worst
    # possible failure mode for a login button.
    app.add_middleware(
        SessionMiddleware,
        secret_key=resolved.session_secret,
        session_cookie="trader_oauth",
        max_age=600,
        same_site="lax",
        https_only=False,
    )
```

and, after `app.state.price_cache`:

```python
    app.state.oauth = build_oauth(resolved)
    app.state.claim_token = ClaimToken(resolved.session_secret)
```

then `app.include_router(auth_module.router)` alongside the others.

- [ ] **Step 6: Run the tests**

Run: `cd backend && uv run pytest tests/auth/ -v`
Expected: PASS

- [ ] **Step 7: Run the whole suite**

Run: `cd backend && uv run pytest -q`
Expected: PASS — including `test_vercel_requirements.py`, which now sees `authlib` reached at module scope.

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth backend/app/deps.py backend/app/main.py backend/tests/auth
git commit -m "Add the six auth routes"
```

---

### Task 7: The `AUTH_MOCK` dev-login route

**Files:**
- Modify: `backend/app/auth/router.py`
- Test: `backend/tests/auth/test_dev_login.py`

**Interfaces:**
- Consumes: `Settings.auth_mock`, `set_session_cookie`
- Produces: `GET /api/auth/dev-login/{user_id}` — 404 `AUTH_PROVIDER_UNAVAILABLE` unless `AUTH_MOCK=true`

**Why:** E2E cannot drive a real Google consent screen. This route is how Playwright signs in — and it is unauthenticated session forgery, so the guard matters more than the feature.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/auth/test_dev_login.py
"""The E2E sign-in shortcut, and the guard that keeps it out of production."""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from tests.conftest import CLIENT_BASE_URL


def _client(settings, **overrides):
    return TestClient(create_app(dataclasses.replace(settings, **overrides)),
                      base_url=CLIENT_BASE_URL)


class TestGuard:
    def test_it_is_absent_by_default(self, settings):
        """Not merely refused -- 404, the same answer an unconfigured provider
        gives, so a probe cannot tell the route exists at all."""
        with _client(settings) as client:
            response = client.get("/api/auth/dev-login/anyone", follow_redirects=False)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"

    def test_auth_mock_false_is_not_enough_to_enable_it(self, settings):
        with _client(settings, auth_mock=False) as client:
            assert client.get("/api/auth/dev-login/anyone").status_code == 404


class TestEnabled:
    def test_it_signs_a_session_for_an_existing_user(self, settings):
        with _client(settings, auth_mock=True) as client:
            user_id = client.get("/api/auth/me").json()["id"]
            client.post("/api/auth/logout")
            assert client.get("/api/auth/me").json()["id"] != user_id

            client.get(f"/api/auth/dev-login/{user_id}", follow_redirects=False)
            assert client.get("/api/auth/me").json()["id"] == user_id

    def test_an_unknown_user_is_refused(self, settings):
        """Signing a cookie for a row that does not exist would hand back a
        session that resolves to nobody and mints a guest on every request."""
        with _client(settings, auth_mock=True) as client:
            response = client.get("/api/auth/dev-login/no-such-user", follow_redirects=False)
            assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/auth/test_dev_login.py -v`
Expected: FAIL — `test_it_signs_a_session_for_an_existing_user` gets 404

- [ ] **Step 3: Implement**

Append to `backend/app/auth/router.py`:

```python
@router.get("/dev-login/{user_id}")
async def dev_login(request: Request, user_id: str):
    """Sign a session for an arbitrary user, with no provider involved.

    E2E only. This is unauthenticated session forgery: anyone who can reach it
    can become any user by guessing an id. It answers 404 rather than 403 when
    `AUTH_MOCK` is unset, so a deployment that has it switched off does not
    advertise that the route exists.
    """
    if not request.app.state.settings.auth_mock:
        raise AuthProviderUnavailableError("Not found.")

    user = await request.app.state.user_store.get(user_id)
    if user is None:
        raise AuthProviderUnavailableError("No such user.")

    response = RedirectResponse("/", status_code=307)
    set_session_cookie(request, response, request.app.state.session_cookie, user.id)
    return response
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/auth/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/router.py backend/tests/auth/test_dev_login.py
git commit -m "Add the AUTH_MOCK dev-login route for E2E"
```

---

### Task 8: The frontend session store

**Files:**
- Create: `frontend/store/useSessionStore.ts`
- Modify: `frontend/lib/types.ts`, `frontend/lib/api/endpoints.ts`
- Test: `frontend/__tests__/store/useSessionStore.test.ts`

**Interfaces:**
- Consumes: `api` (`lib/api/client.ts`)
- Produces:
  - `type Session = { id: string; kind: "guest" | "user"; email: string | null; name: string | null; avatar: string | null; hasActivity: boolean }`
  - `type AuthProvider = { name: string; label: string }`
  - `fetchSession(): Promise<Session>`, `fetchProviders(): Promise<AuthProvider[]>`, `logout(): Promise<void>`, `confirmClaim(token: string): Promise<void>`
  - `useSessionStore` with `session`, `providers`, `sessionVersion`, `load()`, `signOut()`, `claim(token)`

**Why `sessionVersion`:** after a sign-out or a claim, the same URL is a different person's portfolio. Every other store holds the previous identity's data and has no reason to know it went stale. A counter every store keys off is the smallest thing that makes "refetch everything" a single fact rather than a chain of calls each store must remember to make.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/__tests__/store/useSessionStore.test.ts
import { act } from "@testing-library/react";
import { useSessionStore } from "@/store/useSessionStore";
import * as endpoints from "@/lib/api/endpoints";

jest.mock("@/lib/api/endpoints");

const guest = {
  id: "guest-1", kind: "guest" as const, email: null, name: null,
  avatar: null, hasActivity: false,
};

beforeEach(() => {
  useSessionStore.setState({ session: null, providers: [], sessionVersion: 0 });
  jest.resetAllMocks();
});

describe("loading", () => {
  it("holds the session and the providers", async () => {
    (endpoints.fetchSession as jest.Mock).mockResolvedValue(guest);
    (endpoints.fetchProviders as jest.Mock).mockResolvedValue([
      { name: "google", label: "Google" },
    ]);

    await act(async () => { await useSessionStore.getState().load(); });

    expect(useSessionStore.getState().session).toEqual(guest);
    expect(useSessionStore.getState().providers).toHaveLength(1);
  });

  it("survives a provider list that fails", async () => {
    // A deployment with no providers is the normal case, not an error state;
    // the session must still load so the app renders.
    (endpoints.fetchSession as jest.Mock).mockResolvedValue(guest);
    (endpoints.fetchProviders as jest.Mock).mockRejectedValue(new Error("nope"));

    await act(async () => { await useSessionStore.getState().load(); });

    expect(useSessionStore.getState().session).toEqual(guest);
    expect(useSessionStore.getState().providers).toEqual([]);
  });
});

describe("sessionVersion", () => {
  it("bumps on sign out", async () => {
    (endpoints.logout as jest.Mock).mockResolvedValue(undefined);
    (endpoints.fetchSession as jest.Mock).mockResolvedValue(guest);
    (endpoints.fetchProviders as jest.Mock).mockResolvedValue([]);

    const before = useSessionStore.getState().sessionVersion;
    await act(async () => { await useSessionStore.getState().signOut(); });

    expect(useSessionStore.getState().sessionVersion).toBe(before + 1);
  });

  it("bumps on a completed claim", async () => {
    (endpoints.confirmClaim as jest.Mock).mockResolvedValue(undefined);
    (endpoints.fetchSession as jest.Mock).mockResolvedValue({ ...guest, kind: "user" });
    (endpoints.fetchProviders as jest.Mock).mockResolvedValue([]);

    const before = useSessionStore.getState().sessionVersion;
    await act(async () => { await useSessionStore.getState().claim("tok"); });

    expect(useSessionStore.getState().sessionVersion).toBe(before + 1);
  });

  it("does not bump when the claim is refused", async () => {
    // The cookie did not move, so nothing downstream is stale -- a bump would
    // refetch every panel to redraw the same numbers.
    (endpoints.confirmClaim as jest.Mock).mockRejectedValue(new Error("invalid"));

    const before = useSessionStore.getState().sessionVersion;
    await act(async () => {
      await expect(useSessionStore.getState().claim("tok")).rejects.toThrow();
    });

    expect(useSessionStore.getState().sessionVersion).toBe(before);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- useSessionStore`
Expected: FAIL — cannot resolve `@/store/useSessionStore`

- [ ] **Step 3: Add the types**

In `frontend/lib/types.ts`:

```typescript
export interface Session {
  id: string;
  kind: "guest" | "user";
  email: string | null;
  name: string | null;
  avatar: string | null;
  /** Whether signing in would discard anything. Drives the guest hint copy. */
  hasActivity: boolean;
}

export interface AuthProvider {
  name: string;
  label: string;
}
```

- [ ] **Step 4: Add the endpoints**

In `frontend/lib/api/endpoints.ts`:

```typescript
export async function fetchSession(): Promise<Session> {
  return api.get<Session>("/api/auth/me");
}

export async function fetchProviders(): Promise<AuthProvider[]> {
  const body = await api.get<{ providers: AuthProvider[] }>("/api/auth/providers");
  return body.providers;
}

export async function logout(): Promise<void> {
  await api.post<{ ok: boolean }>("/api/auth/logout");
}

export async function confirmClaim(token: string): Promise<void> {
  await api.post<unknown>("/api/auth/claim", { token });
}
```

- [ ] **Step 5: Write the store**

```typescript
// frontend/store/useSessionStore.ts
"use client";

import { create } from "zustand";
import { confirmClaim, fetchProviders, fetchSession, logout } from "@/lib/api/endpoints";
import type { AuthProvider, Session } from "@/lib/types";

interface SessionState {
  session: Session | null;
  providers: AuthProvider[];
  /**
   * Bumped whenever the cookie starts pointing at a different person. Every
   * other store keys its refetch off this: after a sign-out or a claim the
   * same URL is a different portfolio, and the stores holding the previous
   * identity's positions have no other way to learn that.
   */
  sessionVersion: number;
  load: () => Promise<void>;
  signOut: () => Promise<void>;
  claim: (token: string) => Promise<void>;
}

export const useSessionStore = create<SessionState>()((set, get) => ({
  session: null,
  providers: [],
  sessionVersion: 0,

  load: async () => {
    const session = await fetchSession();
    // A deployment with no OAuth credentials is the normal case rather than a
    // failure, so a providers call that goes wrong must not stop the session
    // from loading -- the app renders guest-only, which is correct anyway.
    let providers: AuthProvider[] = [];
    try {
      providers = await fetchProviders();
    } catch {
      providers = [];
    }
    set({ session, providers });
  },

  signOut: async () => {
    await logout();
    await get().load();
    set((state) => ({ sessionVersion: state.sessionVersion + 1 }));
  },

  claim: async (token: string) => {
    // No try/catch: a refused claim leaves the cookie exactly where it was,
    // so nothing downstream is stale and the caller renders the error.
    await confirmClaim(token);
    await get().load();
    set((state) => ({ sessionVersion: state.sessionVersion + 1 }));
  },
}));
```

- [ ] **Step 6: Run the tests**

Run: `cd frontend && npm test -- useSessionStore`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/store/useSessionStore.ts frontend/lib/types.ts \
        frontend/lib/api/endpoints.ts frontend/__tests__/store/useSessionStore.test.ts
git commit -m "Add the frontend session store"
```

---

### Task 9: The account menu and sign-in sheet

**Files:**
- Create: `frontend/components/layout/AccountMenu.tsx`, `frontend/components/layout/SignInSheet.tsx`
- Modify: `frontend/components/layout/Header.tsx`, `frontend/__tests__/lib/theme.test.ts`
- Test: `frontend/__tests__/components/AccountMenu.test.tsx`

**Interfaces:**
- Consumes: `useSessionStore`, `Button` (`components/ui/Button.tsx`), the palette tokens
- Produces: `<AccountMenu />` — the toolbar's right-hand control

**Visual constraints (PLAN.md §2, §10):** system materials, systemBlue as the only interaction colour, continuous corners (10px controls, 14px cards), 0.5px hairline separators. Provider buttons wear the **neutral fill**, not Google or GitHub brand colours — brand colours here would be the only non-systemBlue interaction colour in the app and would read as an advertisement. No new palette tokens.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/__tests__/components/AccountMenu.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AccountMenu } from "@/components/layout/AccountMenu";
import { useSessionStore } from "@/store/useSessionStore";

function setSession(overrides = {}) {
  useSessionStore.setState({
    session: {
      id: "u1", kind: "guest", email: null, name: null,
      avatar: null, hasActivity: false, ...overrides,
    },
    providers: [{ name: "google", label: "Google" }],
    sessionVersion: 0,
  });
}

describe("as a guest", () => {
  it("offers sign in", () => {
    setSession();
    render(<AccountMenu />);
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("says what is at stake once there is something to lose", () => {
    // The hint is the whole reason a guest would sign in; showing it to a
    // guest with an empty portfolio is noise on first paint.
    setSession({ hasActivity: true });
    render(<AccountMenu />);
    expect(screen.getByText(/sign in to keep this portfolio/i)).toBeInTheDocument();
  });

  it("stays quiet on a fresh visit", () => {
    setSession({ hasActivity: false });
    render(<AccountMenu />);
    expect(screen.queryByText(/sign in to keep this portfolio/i)).not.toBeInTheDocument();
  });

  it("lists the configured providers when opened", async () => {
    setSession();
    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByRole("link", { name: /continue with google/i })).toHaveAttribute(
      "href",
      "/api/auth/login/google",
    );
  });

  it("renders no sign-in control when no provider is configured", () => {
    // The zero-config quick start: a button that dead-ends is worse than none.
    setSession();
    useSessionStore.setState({ providers: [] });
    render(<AccountMenu />);
    expect(screen.queryByRole("button", { name: /sign in/i })).not.toBeInTheDocument();
  });
});

describe("as a signed-in user", () => {
  it("shows the account and can sign out", async () => {
    const signOut = jest.fn();
    setSession({ kind: "user", email: "ada@example.com", name: "Ada" });
    useSessionStore.setState({ signOut });

    render(<AccountMenu />);
    await userEvent.click(screen.getByRole("button", { name: /ada/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));

    expect(signOut).toHaveBeenCalled();
  });

  it("falls back to the email when the provider gave no name", () => {
    setSession({ kind: "user", email: "ada@example.com", name: null });
    render(<AccountMenu />);
    expect(screen.getByRole("button", { name: /ada@example.com/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- AccountMenu`
Expected: FAIL — cannot resolve `@/components/layout/AccountMenu`

- [ ] **Step 3: Write the sign-in sheet**

```tsx
// frontend/components/layout/SignInSheet.tsx
"use client";

import type { AuthProvider } from "@/lib/types";

/**
 * The provider list, as a sheet hanging off the toolbar.
 *
 * Each provider is an `<a>`, not a fetch: sign-in is a full-page navigation,
 * which is what makes it work from a static export. A button posting through
 * the API client would land the provider's consent screen inside an XHR.
 *
 * Buttons wear the neutral fill rather than Google's or GitHub's brand
 * colours -- those would be the only non-systemBlue interaction colours in the
 * app, and would read as an advertisement rather than as a control.
 */
export function SignInSheet({ providers }: { providers: AuthProvider[] }) {
  return (
    <div
      role="dialog"
      aria-label="Sign in"
      className="material absolute right-0 top-full z-20 mt-2 w-64 rounded-[14px] p-3 shadow-lg"
    >
      <p className="field-label px-1">Sign in</p>
      <p className="mt-1 px-1 text-[12px] leading-snug text-muted">
        Keeps this portfolio when you change browser.
      </p>
      <div className="mt-3 flex flex-col gap-2">
        {providers.map((provider) => (
          <a
            key={provider.name}
            href={`/api/auth/login/${provider.name}`}
            className="flex h-9 items-center justify-center rounded-[10px] bg-sunk text-[13px] font-semibold text-text transition-colors hover:bg-separator focus-ring"
          >
            Continue with {provider.label}
          </a>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write the account menu**

```tsx
// frontend/components/layout/AccountMenu.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { SignInSheet } from "./SignInSheet";

export function AccountMenu() {
  const session = useSessionStore((s) => s.session);
  const providers = useSessionStore((s) => s.providers);
  const signOut = useSessionStore((s) => s.signOut);
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  // Escape and outside-click close it, because a sheet that can only be
  // dismissed by the control that opened it traps keyboard users.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    const onClick = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  if (!session) return null;

  const signedIn = session.kind === "user";
  const label = signedIn ? (session.name ?? session.email ?? "Account") : "Sign in";

  // Nothing to offer and nothing to show: the zero-config deployment renders
  // no control at all rather than a button that dead-ends.
  if (!signedIn && providers.length === 0) return null;

  return (
    <div className="relative flex items-center gap-3" ref={container}>
      {/* Only once there is something to lose. On a fresh visit the portfolio
          is the seeded $10,000 and the line is pure noise. */}
      {!signedIn && session.hasActivity && (
        <p className="hidden text-[12px] text-muted lg:block">
          Browsing as a guest — sign in to keep this portfolio
        </p>
      )}

      <button
        type="button"
        onClick={() => setOpen((was) => !was)}
        aria-haspopup={signedIn ? "menu" : "dialog"}
        aria-expanded={open}
        className="flex h-8 items-center gap-2 rounded-[10px] px-2.5 text-[13px] font-semibold text-text hover:bg-sunk focus-ring"
      >
        {signedIn && session.avatar ? (
          // eslint-disable-next-line @next/next/no-img-element -- a remote
          // provider avatar, and next/image needs a loader the static export
          // has no server to run.
          <img src={session.avatar} alt="" className="h-6 w-6 rounded-full" />
        ) : (
          <span
            aria-hidden
            className="grid h-6 w-6 place-items-center rounded-full bg-sunk text-[11px] font-bold"
          >
            {(label[0] ?? "?").toUpperCase()}
          </span>
        )}
        <span className="max-w-[10rem] truncate">{label}</span>
      </button>

      {open && !signedIn && <SignInSheet providers={providers} />}

      {open && signedIn && (
        <div
          role="menu"
          className="material absolute right-0 top-full z-20 mt-2 w-56 rounded-[14px] p-1.5 shadow-lg"
        >
          <p className="truncate px-2.5 py-1.5 text-[12px] text-muted">{session.email}</p>
          <div className="mx-2.5 h-px bg-separator" />
          <button
            type="button"
            role="menuitem"
            onClick={() => { setOpen(false); void signOut(); }}
            className="mt-1 w-full rounded-[10px] px-2.5 py-1.5 text-left text-[13px] font-medium text-text hover:bg-sunk focus-ring"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Mount it in the toolbar**

In `frontend/components/layout/Header.tsx`, add `<AccountMenu />` to the right-hand cluster, after the connection status and the appearance control — the account is the least-consulted control there and belongs at the end of the run.

- [ ] **Step 6: Add the contrast pairings**

In `frontend/__tests__/lib/theme.test.ts`, add the new small-text pairings — the muted guest hint on the material, and the sheet's secondary line on the material — to the table that enforces the 4.5:1 floor in both appearances.

- [ ] **Step 7: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/components/layout frontend/__tests__
git commit -m "Add the account menu and sign-in sheet"
```

---

### Task 10: The claim-conflict dialog and the session-version refetch

**Files:**
- Create: `frontend/components/layout/ClaimConflictDialog.tsx`
- Modify: `frontend/app/page.tsx`
- Test: `frontend/__tests__/components/ClaimConflictDialog.test.tsx`

**Interfaces:**
- Consumes: `useSessionStore.claim`, `usePortfolioStore.refresh`, `useWatchlistStore.refresh`, `useChatStore.load`
- Produces: `<ClaimConflictDialog />`, mounted once at the page root

**Behaviour:** renders only when the URL carries `?claim=conflict&token=…`. Confirming calls `claim(token)`; cancelling clears the query string and leaves the guest session untouched. Either way the query parameters are removed, so a reload does not re-prompt.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/__tests__/components/ClaimConflictDialog.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClaimConflictDialog } from "@/components/layout/ClaimConflictDialog";
import { useSessionStore } from "@/store/useSessionStore";

function visit(search: string) {
  window.history.replaceState({}, "", `/${search}`);
}

beforeEach(() => {
  useSessionStore.setState({ claim: jest.fn().mockResolvedValue(undefined) });
});

it("stays closed without the query parameters", () => {
  visit("");
  render(<ClaimConflictDialog />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("opens on a conflict redirect", () => {
  visit("?claim=conflict&token=tok");
  render(<ClaimConflictDialog />);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("names what will be discarded", () => {
  visit("?claim=conflict&token=tok");
  render(<ClaimConflictDialog />);
  expect(screen.getByText(/guest activity will be discarded/i)).toBeInTheDocument();
});

it("claims with the token from the URL", async () => {
  const claim = jest.fn().mockResolvedValue(undefined);
  useSessionStore.setState({ claim });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));

  expect(claim).toHaveBeenCalledWith("tok");
});

it("clears the query string so a reload does not re-prompt", async () => {
  visit("?claim=conflict&token=tok");
  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

  await waitFor(() => expect(window.location.search).toBe(""));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("keeps the guest session when cancelled", async () => {
  const claim = jest.fn();
  useSessionStore.setState({ claim });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

  expect(claim).not.toHaveBeenCalled();
});

it("shows the error and stays open when the claim is refused", async () => {
  useSessionStore.setState({
    claim: jest.fn().mockRejectedValue(new Error("That confirmation is no longer valid.")),
  });
  visit("?claim=conflict&token=tok");

  render(<ClaimConflictDialog />);
  await userEvent.click(screen.getByRole("button", { name: /continue/i }));

  expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- ClaimConflictDialog`
Expected: FAIL — cannot resolve `@/components/layout/ClaimConflictDialog`

- [ ] **Step 3: Implement**

```tsx
// frontend/components/layout/ClaimConflictDialog.tsx
"use client";

import { useEffect, useState } from "react";
import { useSessionStore } from "@/store/useSessionStore";

/**
 * The §5.2 prompt: the one sign-in outcome the server refuses to decide alone.
 *
 * It fires only when a collision actually occurred -- a guest with real
 * activity signing into an account that already exists -- rather than warning
 * before every sign-in. A prompt that appears every time trains people to
 * dismiss it, and the one time it matters they will.
 */
export function ClaimConflictDialog() {
  const claim = useSessionStore((s) => s.claim);
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("claim") === "conflict") setToken(params.get("token"));
  }, []);

  // The token is single-use and short-lived, so leaving it in the URL means a
  // reload re-prompts with something that no longer works.
  const dismiss = () => {
    window.history.replaceState({}, "", window.location.pathname);
    setToken(null);
  };

  if (!token) return null;

  const confirm = async () => {
    setPending(true);
    setError(null);
    try {
      await claim(token);
      dismiss();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That confirmation failed.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="claim-title"
        className="w-full max-w-md rounded-[14px] bg-card p-5 shadow-xl"
      >
        <h2 id="claim-title" className="text-[17px] font-semibold text-text">
          That account already has a portfolio
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">
          Signing in opens the portfolio that already belongs to this account. Your current
          guest activity will be discarded and cannot be recovered.
        </p>
        {error && (
          <p role="alert" className="mt-3 text-[12px] font-medium text-down-text">
            {error}
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={dismiss}
            className="h-9 rounded-[10px] px-3.5 text-[13px] font-semibold text-text hover:bg-sunk focus-ring"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirm}
            disabled={pending}
            className="h-9 rounded-[10px] bg-blue-fill px-3.5 text-[13px] font-semibold text-white disabled:opacity-60 focus-ring"
          >
            {pending ? "Signing in…" : "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Mount it, and refetch on a session change**

In `frontend/app/page.tsx`:

```tsx
  const sessionVersion = useSessionStore((s) => s.sessionVersion);
  const loadSession = useSessionStore((s) => s.load);

  useEffect(() => { void loadSession(); }, [loadSession]);

  // The cookie now points at a different person, so everything on screen
  // belongs to the previous one. Keyed off the counter rather than chained
  // onto sign-out, so any future path that changes identity gets this for
  // free.
  useEffect(() => {
    if (sessionVersion === 0) return;
    void refreshPortfolio();
    void refreshWatchlist();
    void loadChat();
  }, [sessionVersion, refreshPortfolio, refreshWatchlist, loadChat]);
```

and render `<ClaimConflictDialog />` at the root of the returned tree.

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 6: Build the static export**

Run: `cd frontend && npm run build`
Expected: the export completes — the dialog reads `window.location` inside an effect, so prerendering never touches it.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/layout/ClaimConflictDialog.tsx frontend/app/page.tsx \
        frontend/__tests__/components/ClaimConflictDialog.test.tsx
git commit -m "Ask before discarding a guest's work"
```

---

### Task 11: E2E coverage and documentation

**Files:**
- Create: `test/e2e/auth.spec.ts`
- Modify: `test/docker-compose.test.yml`, `planning/PLAN.md`, `planning/API_CONTRACT.md`, `planning/VERCEL_DEPLOYMENT.md`, `README.md`

**Interfaces:**
- Consumes: `AUTH_MOCK=true`, `GET /api/auth/dev-login/{user_id}`

- [ ] **Step 1: Write the E2E spec**

```typescript
// test/e2e/auth.spec.ts
import { expect, test } from "@playwright/test";

test.describe("guest sessions", () => {
  test("two browsers get two portfolios", async ({ browser }) => {
    // The property the whole per-user phase exists for, asserted through the
    // UI rather than the API: separate contexts mean separate cookie jars.
    const first = await browser.newContext();
    const second = await browser.newContext();

    const a = await first.newPage();
    await a.goto("/");
    await a.getByTestId("trade-symbol").fill("AAPL");
    await a.getByTestId("trade-units").fill("2");
    await a.getByRole("button", { name: "Buy" }).click();
    await expect(a.getByTestId("positions-table")).toContainText("AAPL");

    const b = await second.newPage();
    await b.goto("/");
    await expect(b.getByTestId("positions-table")).not.toContainText("AAPL");

    await first.close();
    await second.close();
  });

  test("a portfolio survives a reload", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("trade-symbol").fill("MSFT");
    await page.getByTestId("trade-units").fill("1");
    await page.getByRole("button", { name: "Buy" }).click();
    await expect(page.getByTestId("positions-table")).toContainText("MSFT");

    await page.reload();
    await expect(page.getByTestId("positions-table")).toContainText("MSFT");
  });
});

test.describe("sign-in", () => {
  test("no providers configured means no sign-in control", async ({ page }) => {
    // The E2E stack sets no OAuth credentials, which is also the quick start's
    // configuration -- so this asserts the zero-config path stays clean.
    await page.goto("/");
    await expect(page.getByRole("button", { name: /sign in/i })).toHaveCount(0);
  });

  test("dev-login moves the session to another user", async ({ page, request }) => {
    await page.goto("/");
    const original = (await (await request.get("/api/auth/me")).json()).id;

    await page.request.post("/api/auth/logout");
    await page.goto("/");
    const replacement = (await (await page.request.get("/api/auth/me")).json()).id;
    expect(replacement).not.toBe(original);

    await page.goto(`/api/auth/dev-login/${original}`);
    const restored = (await (await page.request.get("/api/auth/me")).json()).id;
    expect(restored).toBe(original);
  });
});
```

- [ ] **Step 2: Enable the mock in the E2E stack**

In `test/docker-compose.test.yml`, add to the app service's environment:

```yaml
      AUTH_MOCK: "true"
```

- [ ] **Step 3: Run the E2E suite**

Run: `docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit`
Expected: PASS

- [ ] **Step 4: Update the documentation**

`planning/PLAN.md` — a dated revision note under §2 ("First Launch"), because "No login, no signup" is now "no login required":

```markdown
*Revised 2026-08-25: sign-in exists, and is optional. The first run is
unchanged — no login, no signup, a seeded guest portfolio on first request —
but a visitor can now attach that portfolio to a Google or GitHub account so
it survives a change of browser. With no OAuth credentials configured, which
is the default and what `docker compose up` does, no sign-in control is
rendered at all and this section describes the app exactly. See
`docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md` §5 and §9.*
```

Add the six routes to §8's endpoint tables, and the five new variables to §5.

`planning/API_CONTRACT.md` — the request and response shape of each of the six routes, the four new error codes, and the note that `/api/auth/me` is a user-resolving route (it mints) while `/api/auth/providers` is not.

`planning/VERCEL_DEPLOYMENT.md` — the four credential variables and `PUBLIC_BASE_URL` in the environment table, with the callback URLs to register with each provider.

`README.md` — a short "Signing in (optional)" section: what to register with Google and GitHub, which variables to set, and that skipping it leaves the app exactly as it was.

- [ ] **Step 5: Run everything**

Run: `cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add test planning README.md
git commit -m "Cover sign-in end to end, and document it"
```

---

## Self-Review

**Spec coverage.** §5's six routes → Tasks 1, 6, 7. §5.1's matrix → Task 4, every branch. §5.2's claim → Tasks 5, 6, 10. §4's schema → Task 2. §9's frontend → Tasks 8, 9, 10. §10's configuration → Task 1. §11's testing → throughout, plus Task 11.

**Deliberately not covered, and why:**
- §7's shared subsystems (reconciler, snapshot writer, reset, cleanup) shipped with per-user scoping and need no further change: none of them branches on `kind`, and promotion in place means no row moves.
- §12's out-of-scope list is unchanged — no email/password, no account deletion UI, no cross-provider email linking, nothing social.
- **Preview deployments cannot exercise real OAuth.** Vercel gates preview deployments on Hobby, so a provider's callback lands on an SSO wall. Sign-in is verifiable locally (Docker, with credentials) and in production; a preview verifies everything except the round trip through the provider.

**Two things the implementer must not quietly change:**

1. **Do not give the auth routes `CurrentUserDep`** except `/me`. That dependency mints a guest for any caller without one and re-issues the cookie on every response; a callback carrying it emits two competing `Set-Cookie: trader_session` headers.
2. **Do not add an email fallback to `lookup_identity`.** It will look like a bug when the same person signs in with Google and then GitHub and gets two accounts. It is D-6, and the alternative is account takeover wherever a provider does not guarantee the address is verified.

**Open question for the plan's approver, which does not block starting:** the spec does not say what happens when a *signed-in* user's session is used to sign into a second provider that is already linked to a different account. Task 4 resolves it as `SWITCH` — go to the account that owns the identity, leaving the first account intact and reachable by signing in again. That follows D-2, and no data is lost either way, but it is an inference rather than something §5.1 states.
