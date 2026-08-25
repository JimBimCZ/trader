"""The token that carries a contested sign-in across the redirect."""

from __future__ import annotations

import pytest

from app.auth.claim import CLAIM_MAX_AGE, ClaimToken


def _swap(raw: str, index: int) -> str:
    """Change one character, at a position where every bit of it is signed.

    Deliberately not the *last* character. The signature is 20 bytes carried
    in 27 base64 characters, and 27 characters hold 162 bits -- so the final
    character has two spare bits that decode to nothing. When it is "A", the
    swap this test used to make (to "B") flips only those two, the signature
    decodes to the same 20 bytes, and the "tampered" token verifies correctly
    because it is not tampered at all: it is the same token, spelled a second
    way. That is one last character in sixteen, and the timestamp baked into
    each token re-rolls it every run, so the test failed about 6% of the time
    for a reason that had nothing to do with the code under test.

    `tests/identity/test_cookie.py` already mutates the first character for
    this reason.
    """
    replacement = "A" if raw[index] != "A" else "B"
    return raw[:index] + replacement + raw[index + 1 :]


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

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda raw: _swap(raw, 0), id="payload"),
            pytest.param(lambda raw: _swap(raw, raw.rindex(".") + 1), id="signature"),
            pytest.param(lambda raw: raw[:-4], id="truncated"),
        ],
    )
    def test_a_tampered_token_is_rejected(self, token, mutate):
        raw = token.sign("guest-1", "user-9")
        assert token.verify(mutate(raw), "guest-1") is None

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
