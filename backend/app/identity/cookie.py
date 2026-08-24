"""Signing and verifying the session cookie.

Deliberately knows nothing about the database. The cookie carries the user id
and nothing else -- notably not `kind`, because signing in promotes a guest
row in place and a copy of `kind` in the cookie would then be stale. The row
is the only source of truth.
"""

from __future__ import annotations

import logging

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

#: Cookie name, per the spec's session contract.
COOKIE_NAME = "trader_session"

#: 90 days, in seconds.
COOKIE_MAX_AGE = 7776000

_SALT = "trader-session-v1"


class SessionCookie:
    """Signs a user id into a cookie value and reads it back."""

    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)

    def sign(self, user_id: str) -> str:
        return self._serializer.dumps({"uid": user_id})

    def verify(self, raw: str | None, max_age: int = COOKIE_MAX_AGE) -> str | None:
        """Return the user id, or None for anything not validly signed.

        Every rejection returns None rather than raising: an unreadable cookie
        is not an error condition, it is a request that gets a fresh guest.
        """
        if not raw:
            return None
        try:
            payload = self._serializer.loads(raw, max_age=max_age)
        except SignatureExpired:
            return None
        except BadSignature:
            # Worth a log line: in volume this is either a secret rotation or
            # someone probing.
            logger.warning("Rejected a session cookie with a bad signature")
            return None
        if not isinstance(payload, dict):
            return None
        uid = payload.get("uid")
        return uid if isinstance(uid, str) and uid else None
