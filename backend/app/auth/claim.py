"""The short-lived token that carries a contested sign-in across a redirect.

The callback cannot switch the cookie -- doing so would discard a guest's
work without asking -- so it hands the browser a token naming the account it
declined to switch to, and `POST /api/auth/claim` completes the switch once
the user confirms.

The token is bound to the guest session that produced it. It travels in a URL,
which means it can end up in a referrer header, a screenshot, or a pasted
link; bound, a leaked token does nothing for whoever finds it, because their
own session id will not match. Unbound it would be a bearer credential for
someone else's portfolio.
"""

from __future__ import annotations

import logging

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)

#: Ten minutes: long enough to read the dialog and decide, short enough that a
#: token left in a browser history is inert by the time anyone finds it.
CLAIM_MAX_AGE = 600

_SALT = "trader-claim-v1"


class ClaimToken:
    """Signs the pair (guest that asked, account it wants) and reads it back."""

    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)

    def sign(self, guest_id: str, target_id: str) -> str:
        return self._serializer.dumps({"gid": guest_id, "tid": target_id})

    def verify(self, raw: str | None, guest_id: str, max_age: int = CLAIM_MAX_AGE) -> str | None:
        """The account to switch to, or None for anything not usable.

        Every rejection returns None rather than raising: the caller turns
        that into one `CLAIM_TOKEN_INVALID`, and distinguishing "expired" from
        "not yours" in the response would tell a prober which it was.
        """
        if not raw:
            return None
        try:
            # SignatureExpired before BadData: it is a subclass of
            # BadSignature, itself a subclass of BadData, so a narrower branch
            # below would never fire.
            payload = self._serializer.loads(raw, max_age=max_age)
        except SignatureExpired:
            return None
        except BadData:
            logger.warning("Rejected a claim token with a bad signature or payload")
            return None
        if not isinstance(payload, dict) or payload.get("gid") != guest_id:
            return None
        target = payload.get("tid")
        return target if isinstance(target, str) and target else None
