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
    pg_constraint first. Constraint names are unique per relation, not per
    database, so the check must be scoped to the target table via
    `conrelid = '{table}'::regclass` — matching by name alone would find a
    same-named constraint in any other schema and skip the ALTER TABLE,
    silently leaving this table with no foreign key at all.
    """
    name = f"fk_{table}_user"
    return f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = '{name}' AND conrelid = '{table}'::regclass
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
        user_id          TEXT NOT NULL,
        email            TEXT,
        created_at       TEXT NOT NULL,
        PRIMARY KEY (provider, provider_user_id),
        CONSTRAINT fk_oauth_identities_user
            FOREIGN KEY (user_id) REFERENCES users_profile (id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_oauth_user ON oauth_identities (user_id)",
    # 004 -- demo trades are excluded from has_activity(), which gates both
    # the sign-in conflict dialog and whether a demo portfolio may be
    # cleared. Without the flag every seeded guest counts as active: the
    # dialog fires on every sign-in, and the demo it exists to clear never
    # clears. schema.py carries the column too, for a database created fresh.
    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT FALSE",
]


async def run_migrations(db: Database) -> None:
    """Apply every migration in order. Safe on every startup."""
    for index, statement in enumerate(MIGRATIONS, start=1):
        logger.debug("Applying migration %d/%d", index, len(MIGRATIONS))
        await db.execute(statement)
    logger.info("Migrations applied: %d statements", len(MIGRATIONS))
