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


def _default_db_path() -> str:
    """Where SQLite lives when no DATABASE_URL is configured.

    On a serverless platform the only writable directory is /tmp, and it
    belongs to one instance and survives only until that instance is recycled.
    That makes it a usable fallback for a demo and a bad place for anything to
    live permanently — which is what DATABASE_URL is for.
    """
    if os.environ.get("VERCEL"):
        return "/tmp/trader.db"
    return "db/trader.db"


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable snapshot of configuration, read once at startup."""

    db_path: Path = Path("db/trader.db")
    massive_api_key: str = ""
    openrouter_api_key: str = ""
    llm_mock: bool = False

    #: Postgres connection string. When set it replaces SQLite entirely — the
    #: serverless deployment has no disk to keep a database file on.
    database_url: str = ""

    #: Postgres schema to confine every table to. Empty means `public`. The
    #: test suite sets it per test; production has no reason to.
    db_schema: str = ""

    #: "simulator" (stateful GBM on a background task), "deterministic" (the
    #: same process as a pure function of the clock), or "" to decide from the
    #: environment. Nothing runs between requests on a serverless platform, so
    #: the background task never ticks there.
    market_source: str = ""

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

    #: Seconds after which the SSE stream closes itself so the client
    #: reconnects. 0 means never — the container deployment holds the
    #: connection open indefinitely.
    stream_max_seconds: float = 0.0

    # Chat
    chat_history_limit: int = 20
    chat_history_char_budget: int = 8000
    llm_timeout_seconds: float = 30.0

    @property
    def sim_tick_seconds(self) -> float:
        return self.sim_tick_ms / 1000.0

    @property
    def market_source_name(self) -> str:
        if self.massive_api_key.strip():
            return "massive"
        return self.market_source or "simulator"

    @property
    def serverless(self) -> bool:
        """Whether the process is one Vercel will freeze between requests.

        Decides two things that have no other signal: that background tasks are
        pointless, and that the SSE stream has to close itself before the
        platform cuts it off.
        """
        return bool(os.environ.get("VERCEL"))

    @classmethod
    def from_env(cls, db_path: Path | None = None) -> Settings:
        return cls(
            db_path=db_path or Path(os.environ.get("DB_PATH", _default_db_path())),
            massive_api_key=os.environ.get("MASSIVE_API_KEY", ""),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            llm_mock=_env_bool("LLM_MOCK"),
            sim_seed=_env_int("SIM_SEED", None),
            sim_tick_ms=_env_int("SIM_TICK_MS", 500) or 500,
            sim_vol_multiplier=_env_float("SIM_VOL_MULTIPLIER", 1.0),
            massive_poll_seconds=_env_float("MASSIVE_POLL_SECONDS", 15.0),
            database_url=os.environ.get("DATABASE_URL", "").strip(),
            db_schema=os.environ.get("DB_SCHEMA", "").strip(),
            # A serverless deployment has no background task to tick a
            # stateful simulator, so it defaults to the computed one.
            market_source=os.environ.get(
                "MARKET_SOURCE", "deterministic" if os.environ.get("VERCEL") else ""
            ).strip(),
            stream_max_seconds=_env_float("STREAM_MAX_SECONDS", 0.0),
        )
