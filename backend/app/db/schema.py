"""The database schema.

Money and quantities are DOUBLE PRECISION: Postgres REAL is a 4-byte float and
would round a cash balance visibly. Every table carries an explicit `seq`,
because Postgres has no implicit rowid and three queries order by a timestamp
that ties.
"""

from __future__ import annotations

SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS watchlist (
    id       TEXT PRIMARY KEY,
    seq      BIGSERIAL,
    user_id  TEXT NOT NULL DEFAULT 'default',
    ticker   TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id         TEXT PRIMARY KEY,
    seq        BIGSERIAL,
    user_id    TEXT NOT NULL DEFAULT 'default',
    ticker     TEXT NOT NULL,
    quantity   DOUBLE PRECISION NOT NULL,
    avg_cost   DOUBLE PRECISION NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id          TEXT PRIMARY KEY,
    seq         BIGSERIAL,
    user_id     TEXT NOT NULL DEFAULT 'default',
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    DOUBLE PRECISION NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id          TEXT PRIMARY KEY,
    seq         BIGSERIAL,
    user_id     TEXT NOT NULL DEFAULT 'default',
    total_value DOUBLE PRECISION NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    seq        BIGSERIAL,
    user_id    TEXT NOT NULL DEFAULT 'default',
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    actions    TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user_added
    ON watchlist (user_id, added_at);
CREATE INDEX IF NOT EXISTS idx_trades_user_executed
    ON trades (user_id, executed_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_recorded
    ON portfolio_snapshots (user_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_chat_user_created
    ON chat_messages (user_id, created_at);
"""
