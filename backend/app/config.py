"""Environment-driven application settings.

The backend reads environment variables only. python-dotenv loads .env for
local development; in Docker the variables arrive via --env-file, where no
project-root .env exists to read.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in _TRUTHY


def _env_int(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable snapshot of configuration, read once at startup."""

    db_path: Path
    massive_api_key: str = ""
    openrouter_api_key: str = ""
    llm_mock: bool = False

    # Market data
    sim_seed: int | None = None
    sim_tick_ms: int = 500
    sim_vol_multiplier: float = 1.0
    massive_poll_seconds: float = 15.0

    # Domain limits
    watchlist_cap: int = 25
    initial_cash: float = 10_000.0

    # History ring buffer
    history_maxlen: int = 600
    history_poll_seconds: float = 0.5

    # Portfolio snapshots
    snapshot_interval_seconds: float = 30.0
    snapshot_retention_days: int = 7

    # Chat
    chat_history_limit: int = 20
    chat_history_char_budget: int = 8000
    llm_timeout_seconds: float = 30.0

    @property
    def sim_tick_seconds(self) -> float:
        """Simulator tick interval in seconds."""
        return self.sim_tick_ms / 1000.0

    @property
    def market_source_name(self) -> str:
        """Which market data implementation the current config selects."""
        return "massive" if self.massive_api_key.strip() else "simulator"

    @classmethod
    def from_env(cls, db_path: Path | None = None) -> Settings:
        """Build settings from the process environment."""
        return cls(
            db_path=db_path or Path(os.environ.get("DB_PATH", "db/trader.db")),
            massive_api_key=os.environ.get("MASSIVE_API_KEY", ""),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            llm_mock=_env_bool("LLM_MOCK"),
            sim_seed=_env_int("SIM_SEED", None),
            sim_tick_ms=_env_int("SIM_TICK_MS", 500) or 500,
            sim_vol_multiplier=_env_float("SIM_VOL_MULTIPLIER", 1.0),
            massive_poll_seconds=_env_float("MASSIVE_POLL_SECONDS", 15.0),
        )
