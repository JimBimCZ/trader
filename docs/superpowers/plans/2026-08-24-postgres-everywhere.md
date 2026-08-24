# Postgres Everywhere Implementation Plan (Phase 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Postgres the only database engine, delete the SQLite adapter, and add a
forward-only migration runner — with no user-visible behaviour change.

**Architecture:** `PostgresDatabase` already exists and is used whenever `DATABASE_URL` is set.
This phase removes the alternative rather than building anything new: the `Database` ABC collapses
into its single remaining implementation, the test suite moves onto a real Postgres with one
schema per test, and a list of idempotent DDL statements runs at startup so later phases can add
columns to tables Neon already has.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pytest/pytest-asyncio, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md` (§4 migrations, §8
Postgres everywhere, §11 testing)

## Global Constraints

- `DATABASE_URL` is **required**. Startup fails loudly when it is absent — no `/tmp/trader.db` fallback (spec §8).
- `_to_numbered()` (the `?` → `$1` rewriter) is **kept**. Repositories keep writing `?` placeholders. Do not convert queries to `$n` (spec §8).
- `statement_cache_size=0` must stay on every pool: Neon's pooled endpoint runs pgbouncer in transaction mode (existing `postgres.py` docstring).
- Migration statements must be idempotent — `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, guarded `ADD CONSTRAINT`. No version table, no down-migrations (spec §4).
- Money and quantities are `DOUBLE PRECISION`, never `REAL` — Postgres `REAL` is a 4-byte float and visibly rounds a cash balance.
- Ruff: line length 100, `select = ["E","F","I","N","W"]`. Run `uv run ruff check app/ tests/` and `uv run ruff format --check app/ tests/` before every commit.
- This phase changes **no** user-visible behaviour. The app stays single-user on `DEFAULT_USER_ID`.

## File Structure

| File | Responsibility after this phase |
|---|---|
| `backend/app/db/postgres.py` | The only `Database`. Gains optional `search_path` support. |
| `backend/app/db/connection.py` | Shrinks to the `Database` protocol + `init_db`. All SQLite deleted. |
| `backend/app/db/schema.py` | One `SCHEMA_SQL` (the Postgres one). The SQLite copy deleted. |
| `backend/app/db/migrations.py` | **New.** Ordered list of idempotent DDL + `run_migrations()`. |
| `backend/app/db/factory.py` | Shrinks: Postgres or a clear startup error. |
| `backend/tests/conftest.py` | Postgres fixtures, one schema per test. |
| `docker-compose.yml` | Gains a `postgres:16` service with a healthcheck. |
| `.github/workflows/ci.yml` | Gains a Postgres service container. |

---

### Task 1: Move the test suite onto Postgres

Nothing else can be verified until the tests run against the engine we are keeping. This task
changes no application code except adding schema support to the pool.

**Files:**
- Modify: `backend/app/db/postgres.py` (add `search_path` to `connect`, create the schema in `initialize_schema`)
- Modify: `backend/app/config.py` (add `db_schema`)
- Modify: `backend/tests/conftest.py:28-42` (the `db` and `seeded_db` fixtures)
- Modify: `docker-compose.yml` (add the `postgres` service — needed to run the tests locally)

**Interfaces:**
- Consumes: `PostgresDatabase`, `normalize_dsn` from `app.db.postgres`; `init_db`, `seed_if_empty` from `app.db`.
- Produces: `Settings.db_schema: str`; `PostgresDatabase.connect(dsn, max_size=4, search_path="")`; a `db` pytest fixture yielding a `PostgresDatabase` isolated in its own schema.

- [ ] **Step 1: Start a local Postgres to develop against**

Add to `docker-compose.yml`, above the `trader` service:

```yaml
  postgres:
    image: postgres:16-alpine
    container_name: trader-db
    environment:
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: trader
      POSTGRES_DB: trader
    ports:
      # Localhost only, like the app: this database has no meaningful password.
      - "127.0.0.1:5432:5432"
    volumes:
      - trader-pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trader -d trader"]
      interval: 5s
      timeout: 3s
      retries: 10
```

And at the end of the file:

```yaml
volumes:
  trader-pgdata:
```

Run: `docker compose up -d postgres && docker compose exec postgres pg_isready -U trader`
Expected: `accepting connections`

- [ ] **Step 2: Write the failing test for schema-scoped connections**

Create `backend/tests/db/test_search_path.py`:

```python
"""A pool can be confined to one Postgres schema.

This is what gives each test its own isolated tables inside one shared
database, and it is the only reason the app knows the word "schema".
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.postgres import PostgresDatabase, normalize_dsn

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://trader:trader@localhost:5432/trader"
)


class TestSearchPath:
    async def test_tables_land_in_the_named_schema(self):
        schema = f"probe_{uuid.uuid4().hex[:8]}"
        db = await PostgresDatabase.connect(TEST_DSN, search_path=schema)
        try:
            await db.initialize_schema()
            row = await db.fetch_one(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'users_profile'"
            )
            assert row["table_schema"] == schema
        finally:
            await db.close()
            admin = await asyncpg.connect(normalize_dsn(TEST_DSN))
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            await admin.close()

    async def test_no_search_path_uses_the_default_schema(self):
        db = await PostgresDatabase.connect(TEST_DSN)
        try:
            row = await db.fetch_one("SELECT current_schema() AS s")
            assert row["s"] == "public"
        finally:
            await db.close()
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `cd backend && uv run pytest tests/db/test_search_path.py -v`
Expected: FAIL — `TypeError: connect() got an unexpected keyword argument 'search_path'`

- [ ] **Step 4: Add search_path support to the pool**

In `backend/app/db/postgres.py`, replace the `connect` classmethod and `initialize_schema`:

```python
    def __init__(self, pool: asyncpg.Pool, search_path: str = "") -> None:
        self._pool = pool
        self._search_path = search_path

    @classmethod
    async def connect(
        cls, dsn: str, max_size: int = 4, search_path: str = ""
    ) -> PostgresDatabase:
        """Open a pool against Neon's pooled endpoint.

        `statement_cache_size=0` is not optional: the pooled endpoint runs
        pgbouncer in transaction mode, where a prepared statement made on one
        server-side connection is not there on the next, and asyncpg's cache
        would hand out stale statement names.

        `search_path` confines every table to one schema. Production leaves it
        empty and uses `public`; the test suite gives each test its own schema,
        which is what makes them isolated and safe to run in parallel.
        """
        pool = await asyncpg.create_pool(
            normalize_dsn(dsn),
            min_size=0,
            max_size=max_size,
            statement_cache_size=0,
            command_timeout=15.0,
            server_settings={"search_path": search_path} if search_path else None,
        )
        logger.info("Postgres pool ready")
        return cls(pool, search_path)

    async def initialize_schema(self) -> None:
        async with self._pool.acquire() as conn:
            if self._search_path:
                # The pool's search_path names it, but naming a schema does not
                # create it, and CREATE TABLE will not create it either.
                await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self._search_path}"')
            await conn.execute(SCHEMA_SQL)
        logger.info("Postgres schema ready")
```

Note: `POSTGRES_SCHEMA_SQL` is renamed to `SCHEMA_SQL` in Task 3. For now import it as
`from .schema import POSTGRES_SCHEMA_SQL as SCHEMA_SQL` to keep this task self-contained.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/db/test_search_path.py -v`
Expected: 2 passed

- [ ] **Step 6: Add `db_schema` to Settings**

In `backend/app/config.py`, add the field after `database_url`:

```python
    #: Postgres schema to confine every table to. Empty means `public`. The
    #: test suite sets it per test; production has no reason to.
    db_schema: str = ""
```

And in `from_env()`, after the `database_url` line:

```python
            db_schema=os.environ.get("DB_SCHEMA", "").strip(),
```

In `backend/app/db/factory.py`, pass it through:

```python
        return await PostgresDatabase.connect(
            settings.database_url, search_path=settings.db_schema
        )
```

- [ ] **Step 7: Replace the SQLite fixtures**

In `backend/tests/conftest.py`, replace the `settings`, `db`, and `seeded_db` fixtures:

```python
import os
import uuid

import asyncpg

from app.db.postgres import PostgresDatabase, normalize_dsn

TEST_DSN = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://trader:trader@localhost:5432/trader"
)


@pytest.fixture
def db_schema() -> str:
    """A unique schema name per test, so tests never share tables."""
    return f"test_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def settings(db_schema: str) -> Settings:
    """Settings pointed at a throwaway schema, with the LLM mocked."""
    return Settings(
        database_url=TEST_DSN,
        db_schema=db_schema,
        llm_mock=True,
        sim_seed=1234,
    )


@pytest_asyncio.fixture
async def db(settings: Settings):
    """An initialized, unseeded database isolated in its own schema."""
    database = await PostgresDatabase.connect(
        settings.database_url, search_path=settings.db_schema
    )
    await init_db(database)
    yield database
    await database.close()
    admin = await asyncpg.connect(normalize_dsn(settings.database_url))
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{settings.db_schema}" CASCADE')
    finally:
        await admin.close()


@pytest_asyncio.fixture
async def seeded_db(db: Database, settings: Settings):
    """An initialized database with the default profile and watchlist."""
    await seed_if_empty(db, settings)
    return db
```

Update the imports at the top of the file: drop `SqliteDatabase` and `open_connection`, keep
`Database`, `init_db`, `seed_if_empty`. `Settings` no longer takes `db_path`, so the `tmp_path`
argument goes too — but `db_path` is not removed from `Settings` until Task 3, and it has no
default. Give it one now so this task stands alone: in `config.py`, change `db_path: Path` to
`db_path: Path = Path("db/trader.db")`. It stays where it is — it is the first field, and every
field after it already has a default, so the dataclass ordering rule is satisfied.

- [ ] **Step 8: Point `api_client` at the same isolated schema**

Still in `backend/tests/conftest.py`, the `api_client` fixture builds a real app. It must not
touch the public schema. Set the environment the app reads:

```python
@pytest.fixture
def api_client(settings: Settings):
    """A TestClient over a fully started app in its own schema.

    Entering the context manager runs the real lifespan, so the simulator,
    history collector, and snapshot writer are all live.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings)
    with TestClient(app) as client:
        yield client
    # The app owns its pool and closes it in the lifespan; only the schema is
    # left behind, and the `db` fixture is not in play here to drop it.
    import asyncio

    async def _drop() -> None:
        admin = await asyncpg.connect(normalize_dsn(settings.database_url))
        try:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{settings.db_schema}" CASCADE')
        finally:
            await admin.close()

    asyncio.run(_drop())
```

Keep whatever the existing fixture body does beyond this; only the settings source and the
teardown are new.

- [ ] **Step 9: Delete the SQLite-only connection tests**

`backend/tests/db/test_connection.py` tests WAL mode, parent-directory creation, and busy
timeout — all SQLite concepts with no Postgres equivalent. Delete the `TestOpenConnection` class
entirely. Keep any test in that file that exercises `Database.transaction()` or `init_db()`
behaviour, since both survive; run the file to see what remains.

Run: `cd backend && uv run pytest tests/db/ -v`

- [ ] **Step 10: Run the whole suite**

Run: `cd backend && uv run pytest -q`
Expected: all tests pass. Failures here are almost certainly one of two things — a test asserting
SQLite-specific behaviour (delete or rewrite it), or a test relying on `rowid` ordering (Postgres
uses `seq`, which the schema already provides).

- [ ] **Step 11: Lint and commit**

```bash
cd backend && uv run ruff check app/ tests/ && uv run ruff format app/ tests/
cd .. && git add backend/ docker-compose.yml
git commit -m "Run the test suite against a real Postgres

Each test gets its own schema inside one database, which is cheaper than a
container per test and safe to run in parallel. The SQLite-only connection
tests go with it: WAL mode and parent-directory creation have no Postgres
equivalent."
```

---

### Task 2: The migration runner

**Files:**
- Create: `backend/app/db/migrations.py`
- Create: `backend/tests/db/test_migrations.py`
- Modify: `backend/app/db/__init__.py` (export `run_migrations`)
- Modify: `backend/app/main.py:80-82` (call it after `init_db`)

**Interfaces:**
- Consumes: `Database.execute` from `app.db`.
- Produces: `MIGRATIONS: list[str]` and `async def run_migrations(db: Database) -> None` in `app.db.migrations`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/db/test_migrations.py`:

```python
"""The forward-only migration list.

CREATE TABLE IF NOT EXISTS cannot add a column to a table Neon already has,
which is the gap that bites on the second deploy rather than the first. Every
statement here is idempotent, so the list needs no version table.
"""

from __future__ import annotations

import pytest

from app.db.migrations import MIGRATIONS, run_migrations

PER_USER_TABLES = ["watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages"]


class TestIdempotency:
    async def test_running_twice_is_safe(self, db):
        """The second run is what happens on every deploy after the first."""
        await run_migrations(db)
        await run_migrations(db)

    async def test_every_statement_is_individually_repeatable(self, db):
        await run_migrations(db)
        for statement in MIGRATIONS:
            await db.execute(statement)


class TestSeedingSurvivesMigration:
    async def test_a_fresh_database_still_gets_its_watchlist(self, db, settings):
        """Regression: a migration that creates the profile row makes seed_if_empty
        return early, leaving a fresh install with cash and no tickers."""
        from app.db.seed import seed_if_empty

        await seed_if_empty(db, settings)
        await run_migrations(db)

        row = await db.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
        assert row["n"] == 10


class TestForeignKeys:
    @pytest.mark.parametrize("table", PER_USER_TABLES)
    async def test_user_id_references_the_profile(self, db, table):
        await run_migrations(db)
        row = await db.fetch_one(
            """
            SELECT c.confdeltype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE t.relname = ? AND c.contype = 'f' AND n.nspname = current_schema()
            """,
            (table,),
        )
        assert row is not None, f"{table}.user_id has no foreign key"
        assert row["confdeltype"] == "c", "the foreign key must cascade on delete"

    async def test_deleting_a_user_removes_their_rows(self, db, settings):
        """This cascade is what makes guest expiry a single DELETE."""
        from app.db.seed import seed_if_empty

        await seed_if_empty(db, settings)
        await run_migrations(db)
        before = await db.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
        assert before["n"] == 10

        await db.execute("DELETE FROM users_profile WHERE id = ?", ("default",))

        after = await db.fetch_one("SELECT COUNT(*) AS n FROM watchlist")
        assert after["n"] == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/db/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.migrations'`

- [ ] **Step 3: Write the migration list**

Create `backend/app/db/migrations.py`:

```python
"""Forward-only, idempotent schema migrations.

`CREATE TABLE IF NOT EXISTS` in schema.py handles a database that does not
exist yet. It cannot touch one that does — and Neon persists between deploys,
so every change after the first arrives here instead.

Every statement must be safe to run against a database that already has it
applied, because there is no version table recording which have run. That is
the whole trick: idempotency replaces bookkeeping. Statements run in order and
are never edited once deployed — add a new one instead.
"""

from __future__ import annotations

import logging

from .connection import Database

logger = logging.getLogger(__name__)


def _add_user_fk(table: str) -> str:
    """Attach `table.user_id` to `users_profile.id`, cascading on delete.

    Postgres has no ADD CONSTRAINT IF NOT EXISTS, so the DO block checks
    pg_constraint first. The constraint name is derived from the table so each
    one is distinct and the check is exact.
    """
    name = f"fk_{table}_user"
    return f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = '{name}'
        ) THEN
            ALTER TABLE {table}
                ADD CONSTRAINT {name}
                FOREIGN KEY (user_id) REFERENCES users_profile (id) ON DELETE CASCADE;
        END IF;
    END $$;
    """


#: Ordered and append-only. Never edit a statement that has been deployed.
MIGRATIONS: list[str] = [
    # 001 — every per-user row must point at a real profile, so that deleting a
    # user is one statement rather than a six-table transaction.
    *(
        f"UPDATE {table} SET user_id = 'default' WHERE user_id IS NULL"
        for table in ("watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages")
    ),
    *(
        _add_user_fk(table)
        for table in ("watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages")
    ),
]


async def run_migrations(db: Database) -> None:
    """Apply every migration in order. Safe on every startup."""
    for index, statement in enumerate(MIGRATIONS, start=1):
        await db.execute(statement)
    logger.info("Migrations applied: %d statements", len(MIGRATIONS))
```

Note on ordering: the foreign keys cannot be added while a row points at a profile that does not
exist, so seeding must happen *before* the migrations rather than after. Step 5 wires that order.
An earlier draft of this plan created a placeholder profile inside migration 001 instead — which
would have made `seed_if_empty` find the row, return early, and leave a fresh database with a
cash balance and **no watchlist at all**.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/db/test_migrations.py -v`
Expected: 8 passed

- [ ] **Step 5: Wire it into startup**

In `backend/app/db/__init__.py`, add to the imports and `__all__`:

```python
from .migrations import run_migrations
```

In `backend/app/main.py`, inside `lifespan`, between `init_db` and `seed_if_empty`:

```python
    db = await open_database(settings)
    await init_db(db)
    # Seeding first: migration 001 adds foreign keys to users_profile, and every
    # per-user row must already point at a profile that exists.
    await seed_if_empty(db, settings)
    await run_migrations(db)
```

Add `run_migrations` to the existing `from .db import ...` line.

- [ ] **Step 6: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Lint and commit**

```bash
cd backend && uv run ruff check app/ tests/ && uv run ruff format app/ tests/
cd .. && git add backend/
git commit -m "Add a forward-only migration runner

Neon persists between deploys, so CREATE TABLE IF NOT EXISTS stops being
enough the moment a column has to change. Idempotent statements replace a
version table. The first migration attaches every per-user table to
users_profile with ON DELETE CASCADE, which later makes expiring a guest one
statement instead of six."
```

---

### Task 3: Delete SQLite

**Files:**
- Modify: `backend/app/db/connection.py` (delete `SqliteDatabase`, `open_connection`; collapse the ABC)
- Modify: `backend/app/db/schema.py` (delete `SCHEMA_SQL`, rename `POSTGRES_SCHEMA_SQL` → `SCHEMA_SQL`)
- Modify: `backend/app/db/factory.py`, `backend/app/db/__init__.py`
- Modify: `backend/app/config.py` (delete `db_path`, `_default_db_path`)
- Modify: `backend/app/system/service.py:44` (`db_backend`)
- Modify: `backend/app/portfolio/repository.py:122,166`, `backend/app/llm/repository.py:52` (`sequence_column`)
- Modify: `backend/pyproject.toml`, `requirements.txt`

**Interfaces:**
- Consumes: everything from Tasks 1–2.
- Produces: `app.db` exporting `Database` (now an alias for `PostgresDatabase`), `open_database`, `init_db`, `run_migrations`, `seed_if_empty`, `DEFAULT_USER_ID`, `DEFAULT_WATCHLIST`. `Settings` no longer has `db_path`.

- [ ] **Step 1: Write the failing test for a required DATABASE_URL**

Add to `backend/tests/test_config.py` (add the import at the top of the file:
`from app.errors import ConfigurationError`):

```python
class TestDatabaseUrlIsRequired:
    def test_missing_database_url_fails_loudly(self, monkeypatch):
        """A silent ephemeral fallback hides a broken deploy until it matters."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        settings = Settings.from_env()
        with pytest.raises(ConfigurationError, match="DATABASE_URL"):
            settings.require_database_url()

    def test_present_database_url_passes(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
        Settings.from_env().require_database_url()
```

Add `ConfigurationError` to `backend/app/errors.py`:

```python
class ConfigurationError(AppError):
    """The process cannot start with the configuration it was given."""

    status_code, code = 500, "CONFIGURATION_ERROR"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && uv run pytest tests/test_config.py -k DatabaseUrl -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'require_database_url'`

- [ ] **Step 3: Make DATABASE_URL required**

In `backend/app/config.py`: delete `_default_db_path()` and the `db_path` field and its
`from_env` line. Add the method:

```python
    def require_database_url(self) -> str:
        """The connection string, or a startup failure explaining its absence.

        There is deliberately no fallback. A serverless deployment with no
        database used to write to /tmp, which works until the instance is
        recycled and then silently loses the portfolio — a failure that looks
        like a bug in the app rather than a missing variable.
        """
        if not self.database_url:
            raise ConfigurationError(
                "DATABASE_URL is not set. Trader needs a Postgres connection string; "
                "run `docker compose up -d postgres` locally, or set the variable to a "
                "Neon connection string."
            )
        return self.database_url
```

In `backend/app/db/factory.py`, replace the whole body:

```python
"""Opens the database."""

from __future__ import annotations

import logging

from ..config import Settings
from .postgres import PostgresDatabase

logger = logging.getLogger(__name__)


async def open_database(settings: Settings) -> PostgresDatabase:
    """Connect to Postgres. There is no second option."""
    dsn = settings.require_database_url()
    logger.info("Database: Postgres")
    return await PostgresDatabase.connect(dsn, search_path=settings.db_schema)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && uv run pytest tests/test_config.py -k DatabaseUrl -v`
Expected: 2 passed

- [ ] **Step 5: Collapse the Database ABC**

In `backend/app/db/connection.py`, delete `open_connection`, the entire `SqliteDatabase` class,
and the `aiosqlite` import. The `Database` ABC has one implementation left, so replace the class
with an alias and keep `init_db`:

```python
"""Database initialization and the shared user id.

One implementation remains: `PostgresDatabase`. `Database` is kept as a name
so the repositories' type hints read as an intent ("a database") rather than
as a dependency on asyncpg, but it is no longer an abstraction with a second
implementation behind it.
"""

from __future__ import annotations

import logging

from .postgres import PostgresDatabase

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"

#: The only implementation. Kept as an alias so call sites read clearly.
Database = PostgresDatabase


async def init_db(db: Database) -> None:
    """Create the schema if absent. Idempotent, safe on every startup."""
    await db.initialize_schema()
```

Watch for a circular import: `postgres.py` currently does `from .connection import Database`.
Delete that import and have `PostgresDatabase` inherit from nothing.

Delete `sequence_column` from `postgres.py` and replace its three call sites with the literal
`"seq"`:
- `backend/app/portfolio/repository.py:122` and `:166`
- `backend/app/llm/repository.py:52`

Each currently reads `seq = self._db.sequence_column`. Replace with `seq = "seq"`, or inline
`"seq"` into the f-string and delete the local.

- [ ] **Step 6: Delete the SQLite schema**

In `backend/app/db/schema.py`: delete `SCHEMA_SQL` (the SQLite one) and rename
`POSTGRES_SCHEMA_SQL` to `SCHEMA_SQL`. Update its docstring — the comparison to SQLite's REAL and
rowid no longer has a second schema to compare against, so state the reasons directly:

```python
"""The database schema.

Money and quantities are DOUBLE PRECISION: Postgres REAL is a 4-byte float and
would round a cash balance visibly. Every table carries an explicit `seq`,
because Postgres has no implicit rowid and three queries order by a timestamp
that ties.
"""
```

Update the import in `postgres.py` (`from .schema import SCHEMA_SQL`) and remove the temporary
alias added in Task 1 Step 4.

- [ ] **Step 7: Update `app/db/__init__.py`**

```python
"""Database layer: connection, schema, migrations, and seed data.

Public API:
    Database          - the database (Postgres; the alias predates being the only one)
    open_database     - connect, or fail with a clear message
    init_db           - create the schema (idempotent)
    run_migrations    - apply forward-only schema changes (idempotent)
    seed_if_empty     - write default profile and watchlist on a fresh database
    DEFAULT_USER_ID   - the hardcoded single-user id
    DEFAULT_WATCHLIST - the ten starting tickers
"""

from __future__ import annotations

from .connection import DEFAULT_USER_ID, Database, init_db
from .factory import open_database
from .migrations import run_migrations
from .seed import DEFAULT_WATCHLIST, seed_if_empty

__all__ = [
    "DEFAULT_USER_ID",
    "DEFAULT_WATCHLIST",
    "Database",
    "init_db",
    "open_database",
    "run_migrations",
    "seed_if_empty",
]
```

- [ ] **Step 8: Fix the health payload**

In `backend/app/system/service.py`, the `db_backend` key exists to distinguish Postgres from an
ephemeral `/tmp` file that no longer exists. Replace it:

```python
        "db_backend": "postgres",
```

Better: delete the key and update whatever asserts on it. Search first:
`grep -rn "db_backend" backend/ test/ frontend/`

- [ ] **Step 9: Drop the dependency**

In `backend/pyproject.toml`: remove `"aiosqlite>=0.20.0"` from `dependencies`, and move
`"asyncpg>=0.30.0"` from the `postgres` optional group into the main `dependencies` list. Delete
the now-empty `postgres` optional-dependency group and its comment.

In `requirements.txt`: remove the `aiosqlite>=0.20.0` line and update the header comment, which
claims the deployment "talks to Postgres instead of SQLite (no aiosqlite in production, kept for
the /tmp fallback)" — the fallback is gone.

Run: `cd backend && uv lock && uv sync --extra dev`

- [ ] **Step 10: Run everything**

Run: `cd backend && uv run pytest -q && uv run ruff check app/ tests/ && uv run ruff format --check app/ tests/`
Expected: all pass, no lint errors.

Then confirm nothing references the deleted names:
Run: `grep -rn "aiosqlite\|SqliteDatabase\|open_connection\|db_path\|DB_PATH\|sequence_column\|POSTGRES_SCHEMA_SQL" backend/app backend/tests`
Expected: no output.

- [ ] **Step 11: Commit**

```bash
git add backend/ requirements.txt
git commit -m "Delete the SQLite adapter

Two schemas kept in sync by hand was already a drift risk; the auth tables
coming next would have doubled it. With one implementation left, the Database
ABC and its sequence_column indirection have nothing to abstract over.

DATABASE_URL is now required. The /tmp fallback it replaces worked until the
instance was recycled, which made a missing variable look like a bug in the
app."
```

---

### Task 4: Containers and environment

**Files:**
- Modify: `docker-compose.yml` (wire `trader` to `postgres`)
- Modify: `Dockerfile` (drop `DB_PATH`)
- Modify: `test/docker-compose.test.yml` (add a Postgres for E2E)
- Modify: `.env.example`

**Interfaces:**
- Consumes: `DATABASE_URL` from Task 3.
- Produces: a working `docker compose up` with no host-side database file.

- [ ] **Step 1: Wire the app to the database**

In `docker-compose.yml`, in the `trader` service: delete the `volumes:` block (the `./db` bind
mount has nothing to hold now) and add:

```yaml
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://trader:trader@postgres:5432/trader
```

`env_file: - .env` stays, and `environment:` wins over it, so a `DATABASE_URL` in `.env` pointing
at Neon will **not** take effect here. That is deliberate: `docker compose up` should always use
the local database. Document it in the README (Task 6).

- [ ] **Step 2: Drop DB_PATH from the image**

In `Dockerfile`: remove `DB_PATH=/app/db/trader.db` from the `ENV` block and delete the
`RUN mkdir -p /app/db` line and its comment.

- [ ] **Step 3: Give the E2E stack a database**

In `test/docker-compose.test.yml`, add a Postgres service and point the app at it. Replace the
`tmpfs: - /app/db` block (there is no file to throw away any more) with a database that starts
empty on every run:

```yaml
  postgres:
    image: postgres:16-alpine
    container_name: trader-e2e-db
    environment:
      POSTGRES_USER: trader
      POSTGRES_PASSWORD: trader
      POSTGRES_DB: trader
    # No volume: a throwaway database per run, so tests never inherit state.
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trader -d trader"]
      interval: 3s
      timeout: 3s
      retries: 15
```

And in the `trader` service, add to `environment:`:

```yaml
      DATABASE_URL: "postgresql://trader:trader@postgres:5432/trader"
```

plus:

```yaml
    depends_on:
      postgres:
        condition: service_healthy
```

- [ ] **Step 4: Document the variable**

In `.env.example`, add at the top, above `OPENROUTER_API_KEY`:

```bash
# Required: Postgres connection string.
#
# `docker compose up` ignores this and uses its own postgres container; set it
# for running the backend directly on the host, or to point at a Neon database.
# Neon's string carries `channel_binding=require`, which asyncpg rejects — the
# app strips it, so paste the string exactly as Neon gives it to you.
DATABASE_URL=postgresql://trader:trader@localhost:5432/trader
```

- [ ] **Step 5: Verify the stack end to end**

```bash
docker compose down -v
docker compose up -d --build
sleep 20
curl -s localhost:8000/api/health
```

Expected: `{"status":"ok",...,"db_ok":true,...}`.

Then confirm persistence across a restart — the thing the bind mount used to provide:

```bash
curl -s -X POST localhost:8000/api/portfolio/trade \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","quantity":5,"side":"buy"}'
docker compose restart trader
sleep 10
curl -s localhost:8000/api/portfolio | grep AAPL
```

Expected: the AAPL position is still there.

- [ ] **Step 6: Run the E2E suite**

Run: `cd test && docker compose -f docker-compose.test.yml up -d --build && npx playwright test`
Expected: the suite passes as before. Tear down with
`docker compose -f docker-compose.test.yml down -v`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml Dockerfile test/docker-compose.test.yml .env.example
git commit -m "Run Postgres beside the app in both compose stacks

The db/ bind mount and DB_PATH go with SQLite. The compose file pins
DATABASE_URL over anything in .env so that docker compose up always uses its
own container rather than a Neon database someone happened to configure."
```

---

### Task 5: CI

**Files:**
- Modify: `.github/workflows/ci.yml:14-40` (the `backend` job)

- [ ] **Step 1: Add the service container**

In the `backend` job, between `runs-on:` and `defaults:`:

```yaml
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: trader
          POSTGRES_PASSWORD: trader
          POSTGRES_DB: trader
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U trader -d trader"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
```

And give the test step the connection string:

```yaml
      - name: Test
        env:
          TEST_DATABASE_URL: postgresql://trader:trader@localhost:5432/trader
        run: uv run pytest --cov=app --cov-report=term-missing
```

- [ ] **Step 2: Verify**

Push the branch and confirm the backend job goes green. If it fails on connection refused, the
health options are not being honoured — check the indentation of `options:`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Give CI a Postgres to test against"
```

---

### Task 6: Documentation

The `.md` files describe a SQLite app. Several are not merely stale but actively wrong now, which
makes them worse than absent.

**Files:**
- Modify: `README.md` (quick start, config table, architecture diagram, persistence)
- Modify: `planning/PLAN.md` (§3 architecture, §4 directory structure, §7 database, §11 Docker)
- Modify: `planning/DECISIONS.md` (the SQLite decisions)
- Modify: `planning/BACKEND_SUMMARY.md`, `planning/VERCEL_DEPLOYMENT.md`, `planning/REVIEW.md`
- Modify: `backend/CLAUDE.md:53` (the aiosqlite transaction note)
- Modify: `CLAUDE.md` if it names SQLite

- [ ] **Step 1: Find every claim that is now false**

Run: `grep -rn "SQLite\|sqlite\|trader\.db\|db/trader\|aiosqlite\|DB_PATH\|/tmp/trader" README.md CLAUDE.md backend/CLAUDE.md planning/*.md`

Work the list. Every hit is either rewritten or deleted; none is left as-is.

- [ ] **Step 2: README**

- Quick start: `docker compose up` now starts two containers. Say so.
- Replace "Your portfolio persists in `db/trader.db` between restarts. Delete that file, or use
  the in-app reset, to start over." with the Postgres equivalent:
  `docker compose down -v` wipes the database volume; the in-app reset still works.
- Config table: add `DATABASE_URL` as the first row, marked required.
- Architecture block: change `SQLite at db/trader.db (bind-mounted)` to
  `Postgres 16 (compose service, or Neon when deployed)`.

- [ ] **Step 3: planning/PLAN.md**

§3's rationale table has a row "SQLite over Postgres | No auth = no multi-user = no need for a
database server". That reasoning is about to be reversed wholesale by phases 2 and 3, so do not
silently rewrite it — replace the row and add a dated note, matching how §2 records the two 2026-08-18
redesigns:

```markdown
*Revised 2026-08-24: SQLite is gone and the app is multi-user. The row below replaces
"SQLite over Postgres", whose premise — no auth, so no multi-user, so no database server —
stopped holding when accounts arrived. See
`docs/superpowers/specs/2026-08-24-multi-user-oauth-neon-design.md`.*

| Postgres everywhere | One schema and one set of semantics; a serverless deployment has no disk for a database file, and dev/prod parity means no bug class that appears only on Neon |
```

Also update §4 (the `db/` directory no longer holds a runtime database), §7's title and lazy-init
description, and §11's volume wording.

- [ ] **Step 4: planning/DECISIONS.md**

Find the SQLite decisions (D-28 on concurrency, and any on the volume or lazy init). Mark them
superseded with a dated line pointing at the spec rather than deleting them — the file is
provenance, and the header says it is authoritative where it disagrees with PLAN.md, so a silent
edit would leave two documents disagreeing about which is current.

- [ ] **Step 5: The summaries**

`BACKEND_SUMMARY.md` and `VERCEL_DEPLOYMENT.md` describe the shipped state, so they are updated in
place rather than annotated. `VERCEL_DEPLOYMENT.md` in particular records that `DATABASE_URL` was
unset and state was ephemeral — that is exactly what changed.

`REVIEW.md`: check whether any open item is now resolved or moot, and say so rather than leaving
it to be re-investigated.

- [ ] **Step 6: backend/CLAUDE.md**

Line 53 explains transaction locking in terms of "aiosqlite serializes statements, not
transactions". The reason survives but the mechanism changed — the Postgres advisory lock in
`postgres.py` is what serialises writes now. Rewrite it to describe that.

- [ ] **Step 7: Verify no false claims remain**

Run: `grep -rn "SQLite\|sqlite\|trader\.db\|aiosqlite\|DB_PATH" README.md CLAUDE.md backend/CLAUDE.md planning/*.md`
Expected: only historical references that are explicitly marked as superseded.

- [ ] **Step 8: Commit**

```bash
git add README.md CLAUDE.md backend/CLAUDE.md planning/
git commit -m "Update the docs for Postgres everywhere

PLAN.md's 'SQLite over Postgres' row is marked superseded rather than
rewritten: its premise was no-auth-so-no-multi-user, and recording why that
stopped holding is worth more than a clean table."
```

---

## Phase complete

Verify the whole phase before moving to Phase 2:

```bash
cd backend && uv run pytest -q && uv run ruff check app/ tests/
cd .. && docker compose down -v && docker compose up -d --build && sleep 20
curl -s localhost:8000/api/health
cd test && docker compose -f docker-compose.test.yml up -d --build && npx playwright test
```

The app is still single-user. Phase 2 (`docs/superpowers/plans/` — written after this lands)
deletes `DEFAULT_USER_ID` and makes services per-request.
