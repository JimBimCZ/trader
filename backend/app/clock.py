"""Single time seam for the application.

Every module that needs the current time imports it from here rather than
calling time/datetime directly. Tests patch these two functions instead of
patching stdlib globally, which would destabilize asyncio internals.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta


def now_ts() -> float:
    """Current Unix timestamp in float seconds. Matches the SSE payload format."""
    return time.time()


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string. The format for all DB-backed JSON."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_seconds_ago(seconds: int) -> str:
    """The UTC time `seconds` seconds in the past, in `utcnow_iso()`'s format.

    Callers compare this as a *string* against stored `last_seen_at` values
    (`>=` / `<` in SQL), which only orders correctly if the format is
    byte-identical to `utcnow_iso()` -- same suffix, same precision.
    """
    return (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
