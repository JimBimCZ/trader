"""User identity: the session cookie and the user store."""

from .cookie import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie

__all__ = ["COOKIE_MAX_AGE", "COOKIE_NAME", "SessionCookie"]
