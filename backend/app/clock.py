"""Single time seam for the application.

Every module that needs the current time imports it from here rather than
calling time/datetime directly. Tests patch these two functions instead of
patching stdlib globally, which would destabilize asyncio internals.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


def now_ts() -> float:
    """Current Unix timestamp in float seconds. Matches the SSE payload format."""
    return time.time()


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string. The format for all DB-backed JSON."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
