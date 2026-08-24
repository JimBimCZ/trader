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
]


async def run_migrations(db: Database) -> None:
    """Apply every migration in order. Safe on every startup."""
    for index, statement in enumerate(MIGRATIONS, start=1):
        logger.debug("Applying migration %d/%d", index, len(MIGRATIONS))
        await db.execute(statement)
    logger.info("Migrations applied: %d statements", len(MIGRATIONS))
