"""The session cookie is the only thing standing between two users' data.

There is no session table to check against, so a forged or tampered cookie
that verified would hand out someone else's portfolio. These tests are the
whole defence.
"""

from __future__ import annotations

import pytest

from app.identity.cookie import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie

SECRET = "test-secret-not-used-anywhere-real"


class TestRoundTrip:
    def test_a_signed_id_verifies_back_to_itself(self):
        cookie = SessionCookie(SECRET)
        assert cookie.verify(cookie.sign("user-abc")) == "user-abc"

    def test_the_signed_value_is_not_the_bare_id(self):
        """A cookie that were just the id would let anyone name any user."""
        cookie = SessionCookie(SECRET)
        assert cookie.sign("user-abc") != "user-abc"


class TestRejection:
    @pytest.mark.parametrize(
        "bad",
        [
            None,
            "",
            "user-abc",
            "garbage",
            "eyJ1aWQiOiAidXNlci1hYmMifQ",  # unsigned base64 of the payload
        ],
    )
    def test_anything_unsigned_is_refused(self, bad):
        assert SessionCookie(SECRET).verify(bad) is None

    def test_a_tampered_payload_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie.sign("user-abc")
        tampered = ("X" if signed[0] != "X" else "Y") + signed[1:]
        assert cookie.verify(tampered) is None

    def test_a_cookie_signed_with_another_secret_is_refused(self):
        """Rotating SESSION_SECRET must invalidate every existing session."""
        signed = SessionCookie("old-secret").sign("user-abc")
        assert SessionCookie(SECRET).verify(signed) is None

    def test_an_expired_cookie_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie.sign("user-abc")
        assert cookie.verify(signed, max_age=-1) is None


class TestContract:
    def test_the_name_and_lifetime_match_the_spec(self):
        assert COOKIE_NAME == "trader_session"
        assert COOKIE_MAX_AGE == 7776000  # 90 days
