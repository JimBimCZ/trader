"""The session cookie is the only thing standing between two users' data.

There is no session table to check against, so a forged or tampered cookie
that verified would hand out someone else's portfolio. These tests are the
whole defence.
"""

from __future__ import annotations

import pytest
from itsdangerous import URLSafeTimedSerializer

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

    def test_a_value_signed_with_the_right_secret_but_a_different_salt_is_refused(self):
        """The salt is part of the key derivation, same as the secret is."""
        other_salt = URLSafeTimedSerializer(SECRET, salt="a-different-salt")
        signed = other_salt.dumps({"uid": "user-abc"})
        assert SessionCookie(SECRET).verify(signed) is None

    def test_a_non_dict_payload_is_refused(self):
        """Valid JSON, validly signed, but not the shape verify() expects."""
        cookie = SessionCookie(SECRET)
        signed = cookie._serializer.dumps(["user-abc"])
        assert cookie.verify(signed) is None

    def test_a_bare_string_payload_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie._serializer.dumps("user-abc")
        assert cookie.verify(signed) is None

    def test_a_non_string_uid_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie._serializer.dumps({"uid": 12345})
        assert cookie.verify(signed) is None

    def test_an_empty_string_uid_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie._serializer.dumps({"uid": ""})
        assert cookie.verify(signed) is None

    def test_a_whitespace_only_uid_is_refused(self):
        cookie = SessionCookie(SECRET)
        signed = cookie._serializer.dumps({"uid": "   "})
        assert cookie.verify(signed) is None

    def test_a_validly_signed_but_undecodable_payload_is_refused(self):
        """White-box regression test for a real gap: `BadPayload` (raised when

        the HMAC checks out but the payload itself won't base64/JSON-decode)
        is a sibling of `BadSignature` under `BadData`, not a subclass of it.
        A handler that only catches `BadSignature` lets this one escape as an
        unhandled exception instead of returning None.
        """
        cookie = SessionCookie(SECRET)
        signer = cookie._serializer.make_signer()
        corrupt = signer.sign(b"not-valid-base64-json!!!").decode()
        assert cookie.verify(corrupt) is None


class TestContract:
    def test_the_name_and_lifetime_match_the_spec(self):
        assert COOKIE_NAME == "trader_session"
        assert COOKIE_MAX_AGE == 7776000  # 90 days
