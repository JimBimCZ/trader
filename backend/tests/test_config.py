"""Tests for environment-driven settings."""

from __future__ import annotations

import logging

import pytest

from app.config import Settings
from app.errors import ConfigurationError


class TestFromEnv:
    def test_defaults_with_an_empty_environment(self, monkeypatch):
        """Missing variables fall back to documented defaults."""
        for name in ("MASSIVE_API_KEY", "OPENROUTER_API_KEY", "LLM_MOCK", "SIM_SEED"):
            monkeypatch.delenv(name, raising=False)
        s = Settings.from_env()
        assert s.llm_mock is False
        assert s.sim_seed is None
        assert s.sim_tick_ms == 500
        assert s.watchlist_cap == 25
        assert s.initial_cash == 10_000.0

    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on"])
    def test_llm_mock_truthy_variants(self, monkeypatch, raw):
        """Several spellings of true all enable mock mode."""
        monkeypatch.setenv("LLM_MOCK", raw)
        assert Settings.from_env().llm_mock is True

    @pytest.mark.parametrize("raw", ["false", "0", "no", "", "banana"])
    def test_llm_mock_falsy_variants(self, monkeypatch, raw):
        """Anything else leaves mock mode off."""
        monkeypatch.setenv("LLM_MOCK", raw)
        assert Settings.from_env().llm_mock is False

    def test_sim_seed_parses(self, monkeypatch):
        """A numeric seed is read as an int."""
        monkeypatch.setenv("SIM_SEED", "42")
        assert Settings.from_env().sim_seed == 42

    def test_invalid_sim_seed_falls_back_to_none(self, monkeypatch):
        """A non-numeric seed does not crash startup."""
        monkeypatch.setenv("SIM_SEED", "not-a-number")
        assert Settings.from_env().sim_seed is None

    @pytest.mark.parametrize("raw", ["-1", "-365", "0"])
    def test_a_non_positive_guest_ttl_is_floored_at_a_day(self, monkeypatch, raw):
        """A negative TTL puts the cleanup cutoff in the *future*, so
        `last_seen_at < cutoff` matches every guest and the next sweep cascades
        away every watchlist, position, trade, chat message and snapshot in the
        database. A typo'd sign in a dashboard variable must not be total data
        loss.
        """
        monkeypatch.setenv("GUEST_TTL_DAYS", raw)
        assert Settings.from_env().guest_ttl_days >= 1


class TestDerivedProperties:
    def test_tick_seconds(self):
        """Tick milliseconds convert to seconds for the simulator."""
        assert Settings(sim_tick_ms=250).sim_tick_seconds == 0.25

    def test_market_source_name_is_simulator_without_a_key(self):
        """No Massive key means the simulator, matching the market factory."""
        assert Settings().market_source_name == "simulator"

    def test_market_source_name_ignores_whitespace_only_key(self):
        """A whitespace-only key is treated as absent, as the factory does."""
        s = Settings(massive_api_key="   ")
        assert s.market_source_name == "simulator"

    def test_market_source_name_is_massive_with_a_key(self):
        """A real key selects the Massive source."""
        s = Settings(massive_api_key="abc123")
        assert s.market_source_name == "massive"


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


class TestVolatilityMultiplier:
    def test_defaults_to_one(self, monkeypatch):
        """Unset means the model behaves exactly as documented."""
        monkeypatch.delenv("SIM_VOL_MULTIPLIER", raising=False)
        assert Settings.from_env().sim_vol_multiplier == 1.0

    def test_parses_a_float(self, monkeypatch):
        monkeypatch.setenv("SIM_VOL_MULTIPLIER", "12.5")
        assert Settings.from_env().sim_vol_multiplier == 12.5

    def test_invalid_value_falls_back_rather_than_crashing_startup(self, monkeypatch):
        monkeypatch.setenv("SIM_VOL_MULTIPLIER", "very-volatile")
        assert Settings.from_env().sim_vol_multiplier == 1.0


class TestSessionSecret:
    def test_reads_session_secret_when_set(self, monkeypatch):
        monkeypatch.setenv("SESSION_SECRET", "a-real-secret")
        assert Settings.from_env().session_secret == "a-real-secret"

    def test_generates_an_ephemeral_secret_and_warns_when_unset(self, monkeypatch, caplog):
        """No SESSION_SECRET must not silently produce a blank or missing one.

        The warning matters as much as the fallback: there is no session
        table, so the cookie is the only pointer to a user's row -- an
        ephemeral secret regenerated on every restart signs out every user
        and permanently orphans every guest portfolio.
        """
        monkeypatch.delenv("SESSION_SECRET", raising=False)
        with caplog.at_level(logging.WARNING, logger="app.config"):
            settings = Settings.from_env()
        assert settings.session_secret
        assert len(settings.session_secret) > 20
        assert "SESSION_SECRET" in caplog.text
        assert "orphan" in caplog.text

    def test_whitespace_only_session_secret_falls_back_to_ephemeral(self, monkeypatch, caplog):
        """A blank value is as absent as no value at all."""
        monkeypatch.setenv("SESSION_SECRET", "   ")
        with caplog.at_level(logging.WARNING, logger="app.config"):
            settings = Settings.from_env()
        assert settings.session_secret.strip() == settings.session_secret
        assert settings.session_secret != ""

    def test_two_ephemeral_secrets_differ(self, monkeypatch):
        """Otherwise 'ephemeral' would be a lie -- it would be one fixed value."""
        monkeypatch.delenv("SESSION_SECRET", raising=False)
        first = Settings.from_env().session_secret
        second = Settings.from_env().session_secret
        assert first != second


class TestCleanupSecret:
    """CLEANUP_SECRET and CRON_SECRET both guard /api/admin/cleanup.

    CRON_SECRET is Vercel's own convention -- it auto-attaches an
    `Authorization: Bearer $CRON_SECRET` header to every Cron invocation, and
    a Vercel deployment should not need a second, duplicate variable just for
    this app's route.
    """

    def test_reads_cleanup_secret_when_only_it_is_set(self, monkeypatch):
        monkeypatch.setenv("CLEANUP_SECRET", "cleanup-value")
        monkeypatch.delenv("CRON_SECRET", raising=False)
        assert Settings.from_env().cleanup_secret == "cleanup-value"

    def test_falls_back_to_cron_secret_when_cleanup_secret_is_unset(self, monkeypatch):
        monkeypatch.delenv("CLEANUP_SECRET", raising=False)
        monkeypatch.setenv("CRON_SECRET", "cron-value")
        assert Settings.from_env().cleanup_secret == "cron-value"

    def test_cleanup_secret_takes_precedence_over_cron_secret(self, monkeypatch):
        """Both set: CLEANUP_SECRET wins, since it names this route directly."""
        monkeypatch.setenv("CLEANUP_SECRET", "cleanup-value")
        monkeypatch.setenv("CRON_SECRET", "cron-value")
        assert Settings.from_env().cleanup_secret == "cleanup-value"

    def test_defaults_to_empty_when_neither_is_set(self, monkeypatch):
        monkeypatch.delenv("CLEANUP_SECRET", raising=False)
        monkeypatch.delenv("CRON_SECRET", raising=False)
        assert Settings.from_env().cleanup_secret == ""
