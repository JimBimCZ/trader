"""The §5.1 matrix, in full. No database, no provider, no HTTP."""

from __future__ import annotations

from app.auth.resolution import Outcome, decide


class TestKnownIdentity:
    """The identity has signed in before, so an account already exists (D-2:
    it wins)."""

    def test_an_untouched_guest_is_switched_silently(self):
        decision = decide(
            linked_user_id="user-1",
            session_user_id="guest-9",
            session_kind="guest",
            session_has_activity=False,
        )
        assert decision == (Outcome.SWITCH, "user-1")

    def test_a_used_guest_produces_a_conflict(self):
        """The only case that cannot be decided server-side: real activity is
        about to be discarded, so the user is asked first."""
        decision = decide(
            linked_user_id="user-1",
            session_user_id="guest-9",
            session_kind="guest",
            session_has_activity=True,
        )
        assert decision == (Outcome.CONFLICT, "user-1")

    def test_signing_in_as_yourself_is_never_a_conflict(self):
        """Re-authenticating an account you are already in must not warn about
        discarding that account's own activity."""
        decision = decide(
            linked_user_id="user-1",
            session_user_id="user-1",
            session_kind="user",
            session_has_activity=True,
        )
        assert decision == (Outcome.SWITCH, "user-1")

    def test_a_signed_in_user_switching_accounts_is_not_asked(self):
        """Their activity is safe in the account they are leaving -- nothing
        is discarded, so there is nothing to confirm."""
        decision = decide(
            linked_user_id="user-1",
            session_user_id="user-2",
            session_kind="user",
            session_has_activity=True,
        )
        assert decision == (Outcome.SWITCH, "user-1")

    def test_no_session_at_all_is_a_switch(self):
        decision = decide(
            linked_user_id="user-1",
            session_user_id=None,
            session_kind=None,
            session_has_activity=False,
        )
        assert decision == (Outcome.SWITCH, "user-1")


class TestNewIdentity:
    """First time this provider identity has been seen."""

    def test_a_guest_is_promoted_in_place(self):
        """Activity is irrelevant here -- promotion keeps every row, so there
        is nothing to lose and nothing to ask about."""
        for has_activity in (True, False):
            decision = decide(
                linked_user_id=None,
                session_user_id="guest-9",
                session_kind="guest",
                session_has_activity=has_activity,
            )
            assert decision == (Outcome.PROMOTE, "guest-9")

    def test_a_signed_in_user_gets_a_second_identity_on_the_same_row(self):
        """Signing in with GitHub while already signed in with Google links
        both to one account rather than stranding the portfolio."""
        decision = decide(
            linked_user_id=None,
            session_user_id="user-1",
            session_kind="user",
            session_has_activity=True,
        )
        assert decision == (Outcome.PROMOTE, "user-1")

    def test_no_session_creates_a_user(self):
        decision = decide(
            linked_user_id=None,
            session_user_id=None,
            session_kind=None,
            session_has_activity=False,
        )
        assert decision == (Outcome.CREATE, None)
