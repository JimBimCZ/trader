"""Tests for environment-driven settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


class TestFromEnv:
    def test_defaults_with_an_empty_environment(self, monkeypatch):
        """Missing variables fall back to documented defaults."""
        for name in ("MASSIVE_API_KEY", "OPENROUTER_API_KEY", "LLM_MOCK", "SIM_SEED", "DB_PATH"):
            monkeypatch.delenv(name, raising=False)
        s = Settings.from_env()
        assert s.db_path == Path("db/trader.db")
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

    def test_db_path_override(self, monkeypatch):
        """DB_PATH relocates the database file."""
        monkeypatch.setenv("DB_PATH", "/tmp/other.db")
        assert Settings.from_env().db_path == Path("/tmp/other.db")


class TestDerivedProperties:
    def test_tick_seconds(self, tmp_path):
        """Tick milliseconds convert to seconds for the simulator."""
        assert Settings(db_path=tmp_path / "d", sim_tick_ms=250).sim_tick_seconds == 0.25

    def test_market_source_name_is_simulator_without_a_key(self, tmp_path):
        """No Massive key means the simulator, matching the market factory."""
        assert Settings(db_path=tmp_path / "d").market_source_name == "simulator"

    def test_market_source_name_ignores_whitespace_only_key(self, tmp_path):
        """A whitespace-only key is treated as absent, as the factory does."""
        s = Settings(db_path=tmp_path / "d", massive_api_key="   ")
        assert s.market_source_name == "simulator"

    def test_market_source_name_is_massive_with_a_key(self, tmp_path):
        """A real key selects the Massive source."""
        s = Settings(db_path=tmp_path / "d", massive_api_key="abc123")
        assert s.market_source_name == "massive"


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
