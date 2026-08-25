"""The token that carries a contested sign-in across the redirect."""

from __future__ import annotations

import pytest

from app.auth.claim import CLAIM_MAX_AGE, ClaimToken


@pytest.fixture
def token() -> ClaimToken:
    return ClaimToken("secret-for-tests")


class TestRoundTrip:
    def test_a_token_verifies_for_the_guest_that_produced_it(self, token):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw, "guest-1") == "user-9"


class TestRejection:
    def test_another_session_cannot_use_it(self, token):
        """The token travels in a URL -- a referrer, a screenshot, a shared
        link. Bound to its guest, a leaked one is useless to anyone else;
        unbound, it is a bearer credential for someone else's portfolio."""
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw, "guest-2") is None

    def test_a_tampered_token_is_rejected(self, token):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw[:-1] + ("A" if raw[-1] != "A" else "B"), "guest-1") is None

    def test_another_secret_cannot_mint_one(self, token):
        forged = ClaimToken("a-different-secret").sign("guest-1", "user-9")
        assert token.verify(forged, "guest-1") is None

    def test_an_expired_token_is_rejected(self, token):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(raw, "guest-1", max_age=-1) is None

    @pytest.mark.parametrize("raw", [None, "", "not-a-token"])
    def test_junk_is_rejected_without_raising(self, raw, token):
        assert token.verify(raw, "guest-1") is None


def test_the_window_is_short():
    """Long enough to read a dialog, short enough that a token left in
    somebody's history is inert by the time it is found."""
    assert CLAIM_MAX_AGE == 600
