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
