"""The dialect seam that lets the repositories stay SQLite-flavoured.

Everything here is pure translation, so it runs without a Postgres to connect
to — which is the point: the repositories' SQL is shared, and only these two
functions know that two dialects exist.
"""

from __future__ import annotations

import pytest

from app.db.postgres import PostgresDatabase, _to_numbered, normalize_dsn


class TestPlaceholders:
    def test_each_placeholder_is_numbered_in_order(self):
        assert (
            _to_numbered("SELECT ticker FROM watchlist WHERE user_id = ? AND ticker = ?")
            == "SELECT ticker FROM watchlist WHERE user_id = $1 AND ticker = $2"
        )

    def test_sql_without_placeholders_is_untouched(self):
        assert _to_numbered("SELECT 1") == "SELECT 1"

    def test_a_question_mark_inside_a_literal_is_left_alone(self):
        assert _to_numbered("SELECT ? WHERE note = 'why?'") == "SELECT $1 WHERE note = 'why?'"

    def test_the_upsert_the_repositories_use_survives(self):
        translated = _to_numbered(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, ticker) "
            "DO UPDATE SET quantity = excluded.quantity"
        )
        assert "VALUES ($1, $2, $3, $4, $5, $6)" in translated
        assert "excluded.quantity" in translated


class TestDsn:
    def test_channel_binding_is_dropped(self):
        """asyncpg raises on it, and Neon puts it in every connection string."""
        normalized = normalize_dsn(
            "postgresql://u:p@host/db?sslmode=require&channel_binding=require"
        )
        assert normalized == "postgresql://u:p@host/db?sslmode=require"

    def test_sslmode_is_kept(self):
        assert "sslmode=require" in normalize_dsn("postgresql://u:p@host/db?sslmode=require")

    def test_a_leading_dropped_parameter_leaves_valid_separators(self):
        normalized = normalize_dsn(
            "postgresql://u:p@host/db?channel_binding=require&sslmode=require"
        )
        assert normalized == "postgresql://u:p@host/db?sslmode=require"

    def test_a_plain_dsn_is_unchanged(self):
        assert normalize_dsn("postgresql://u:p@host/db") == "postgresql://u:p@host/db"


class TestDialect:
    def test_postgres_orders_by_an_explicit_sequence(self):
        """Postgres has no rowid, so the three tie-broken queries need a column."""
        assert PostgresDatabase.sequence_column == "seq"

    def test_the_schema_declares_that_column(self):
        from app.db.schema import POSTGRES_SCHEMA_SQL

        for table in ("trades", "portfolio_snapshots", "chat_messages", "watchlist"):
            statement = POSTGRES_SCHEMA_SQL.split(f"CREATE TABLE IF NOT EXISTS {table}")[1]
            assert "seq" in statement.split(");")[0]

    @pytest.mark.parametrize("table", ["users_profile", "positions", "trades"])
    def test_money_is_not_stored_as_a_four_byte_float(self, table):
        """Postgres REAL would round a cash balance where SQLite's REAL does not."""
        from app.db.schema import POSTGRES_SCHEMA_SQL

        statement = POSTGRES_SCHEMA_SQL.split(f"CREATE TABLE IF NOT EXISTS {table}")[1]
        body = statement.split(");")[0]
        assert " REAL" not in body
