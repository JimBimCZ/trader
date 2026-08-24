"""The user record, as the rest of the app sees it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """One row of users_profile.

    `kind` distinguishes a guest from a signed-in user. It is read from the
    row on every request rather than carried in the cookie, so promoting a
    guest in place takes effect immediately.
    """

    id: str
    cash_balance: float
    kind: str
    created_at: str
    last_seen_at: str
