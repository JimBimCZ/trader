"""Environment-driven application settings.

The backend reads environment variables only. python-dotenv loads .env for
local development; in Docker the variables arrive via --env-file, where no
project-root .env exists to read.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass

from .errors import ConfigurationError

logger = logging.getLogger(__name__)

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

    massive_api_key: str = ""
    openrouter_api_key: str = ""
    llm_mock: bool = False

    #: Postgres connection string. Required — see `require_database_url`.
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

    #: Bounds simulator work and Massive polling cost across all users.
    market_capacity: int = 100
    initial_cash: float = 10_000.0

    #: Signs the session cookie that identifies a user. See `from_env` for
    #: what happens when it is unset.
    session_secret: str = ""

    #: Days of inactivity after which a guest (never a signed-in user) is
    #: deleted, cascading away its watchlist, positions, trades, and chat.
    guest_ttl_days: int = 7

    #: Minimum gap between `last_seen_at` writes for the same user, so an
    #: unthrottled hot path doesn't turn every GET into a Neon round trip.
    last_seen_throttle_seconds: float = 300.0

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

    @classmethod
    def from_env(cls) -> Settings:
        # A generated secret is correct for local dev and catastrophic in
        # production: it changes on every restart, which signs out every user
        # and permanently orphans every guest portfolio, since the cookie is
        # the only pointer to the row.
        session_secret = os.environ.get("SESSION_SECRET", "").strip()
        if not session_secret:
            session_secret = secrets.token_urlsafe(32)
            logger.warning(
                "SESSION_SECRET is not set; generated an ephemeral one. Every "
                "restart will sign out all users and orphan every guest "
                "portfolio. Set it before deploying."
            )
        return cls(
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
            session_secret=session_secret,
            guest_ttl_days=_env_int("GUEST_TTL_DAYS", 7) or 7,
        )
