"""The sign-in decision, as a function of facts already gathered.

Kept free of I/O on purpose: this matrix is the part of sign-in that is
easiest to get subtly wrong, and a pure function makes every branch testable
without a database, a provider, or a browser. The router gathers the facts and
carries out the verdict; it holds no branching of its own.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class Outcome(StrEnum):
    #: Attach this identity to the session's row and mark it a user. The id
    #: does not change, so the portfolio comes along.
    PROMOTE = "promote"
    #: Point the cookie at an existing account. The session's own row is left
    #: alone -- an untouched guest, which expires on its own.
    SWITCH = "switch"
    #: No session to build on: create a seeded row and link the identity.
    CREATE = "create"
    #: Would discard real activity. Ask first (§5.2).
    CONFLICT = "conflict"


class Decision(NamedTuple):
    """The verdict, as a pair.

    A NamedTuple rather than a dataclass so it compares equal to a plain
    tuple: every test in this module states its expectation as
    `(outcome, target)`, and a frozen dataclass would quietly fail all of
    them by returning NotImplemented against a tuple.
    """

    outcome: Outcome
    #: The row to end up in. None only for CREATE, which has none yet.
    target_user_id: str | None


def decide(
    *,
    linked_user_id: str | None,
    session_user_id: str | None,
    session_kind: str | None,
    session_has_activity: bool,
) -> Decision:
    """Resolve a completed OAuth callback to one of four actions.

    `linked_user_id` is the account this provider identity already belongs to,
    or None if it is new. The session arguments describe whoever is holding
    the cookie right now, which may be nobody.
    """
    if linked_user_id is None:
        # A new identity never displaces anything: either it joins the row the
        # caller is already in -- promoting a guest, or adding a second
        # provider to a user -- or there is no row and we make one.
        if session_user_id is not None:
            return Decision(Outcome.PROMOTE, session_user_id)
        return Decision(Outcome.CREATE, None)

    # The identity is known, so that account wins (D-2). The only question is
    # whether anything is lost by leaving the current session behind.
    losing_something = (
        session_kind == "guest" and session_has_activity and session_user_id != linked_user_id
    )
    if losing_something:
        return Decision(Outcome.CONFLICT, linked_user_id)
    return Decision(Outcome.SWITCH, linked_user_id)
