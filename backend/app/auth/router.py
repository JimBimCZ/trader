"""Sign-in routes.

HTTP only: the decision lives in `resolution.py` and the writes live in
`UserStore`. What is here is gathering facts, carrying out a verdict, and
setting exactly one cookie.

None of these routes uses `CurrentUserDep` except `/me`. That dependency mints
a guest for any caller without one and re-issues the session cookie on every
response -- so a callback that depended on it would emit two `Set-Cookie:
trader_session` headers, one naming the old user and one the new, and leave
the browser to pick. These routes read the cookie themselves and write it
once, on the response they return.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..deps import CurrentUserDep, clear_session_cookie, set_session_cookie
from ..errors import (
    AuthExchangeFailedError,
    AuthProviderUnavailableError,
    AuthStateInvalidError,
    ClaimTokenInvalidError,
)
from ..identity import COOKIE_NAME, User
from .providers import PROVIDER_LABELS, OAuthProfile
from .resolution import Outcome, decide

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ClaimRequest(BaseModel):
    token: str


def _client(request: Request, provider: str):
    """The Authlib client for a provider, or 404 if this deployment has none."""
    client = request.app.state.oauth.create_client(provider)
    if client is None or provider not in PROVIDER_LABELS:
        raise AuthProviderUnavailableError(f"{provider} sign-in is not configured here.")
    return client


async def _session_user(request: Request) -> User | None:
    """Whoever holds the cookie right now, without minting anybody.

    Deliberately not `get_current_user`: arriving at a callback with no
    session is normal (a cookie-less browser, or one that cleared it
    mid-flow), and minting a guest to immediately discard it would write
    twelve rows per sign-in.
    """
    user_id = request.app.state.session_cookie.verify(request.cookies.get(COOKIE_NAME))
    if not user_id:
        return None
    return await request.app.state.user_store.get(user_id)


def _callback_url(request: Request, provider: str) -> str:
    """Where the provider should send the browser back.

    `PUBLIC_BASE_URL` wins when set, because a proxy that rewrites the host
    makes `request.url_for` produce an origin the provider will reject -- and
    the resulting error names neither the cause nor this setting.
    """
    configured = request.app.state.settings.public_base_url.strip().rstrip("/")
    if configured:
        return f"{configured}/api/auth/callback/{provider}"
    return str(request.url_for("oauth_callback", provider=provider))


async def _complete_exchange(request: Request, provider: str) -> OAuthProfile:
    """Trade the code for a token and reduce the provider's answer to a profile.

    Replaced wholesale in tests: everything below it -- the decision, the
    store writes, the cookie -- is exercised for real, and only the network
    call to a third party is stubbed.
    """
    client = _client(request, provider)
    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        # Authlib raises the same class for a mismatched state and a refused
        # exchange; the message distinguishes them, the type does not. State
        # problems are ordinary (a bookmarked callback, a back button, a
        # redeploy that rotated the secret) and must not read as an outage.
        if "state" in str(exc).lower():
            logger.info("Rejected an OAuth callback with bad state: %s", exc)
            raise AuthStateInvalidError("That sign-in link has expired. Please try again.") from exc
        logger.warning("OAuth exchange failed for %s: %s", provider, exc)
        raise AuthExchangeFailedError(f"{provider} did not complete the sign-in.") from exc

    if provider == "google":
        info = token.get("userinfo") or await client.userinfo(token=token)
        return OAuthProfile(
            provider="google",
            subject=str(info["sub"]),
            email=info.get("email"),
            name=info.get("name"),
            avatar=info.get("picture"),
        )

    # GitHub: no id_token, and /user omits a private address, so the verified
    # primary comes from a second call. A user with no public and no verified
    # address signs in fine and simply has no email.
    profile_response = await client.get("user", token=token)
    profile_response.raise_for_status()
    info = profile_response.json()
    email = info.get("email")
    if not email:
        emails_response = await client.get("user/emails", token=token)
        if emails_response.status_code == 200:
            email = next(
                (
                    entry["email"]
                    for entry in emails_response.json()
                    if entry.get("primary") and entry.get("verified")
                ),
                None,
            )
    return OAuthProfile(
        provider="github",
        subject=str(info["id"]),
        email=email,
        name=info.get("name") or info.get("login"),
        avatar=info.get("avatar_url"),
    )


@router.get("/providers")
async def providers(request: Request) -> dict:
    """What this deployment can offer, so the UI hides what it cannot."""
    configured = request.app.state.settings.configured_providers
    return {"providers": [{"name": name, "label": PROVIDER_LABELS[name]} for name in configured]}


@router.get("/login/{provider}")
async def login(request: Request, provider: str):
    """Send the browser to the provider.

    A full-page navigation rather than a popup: that is what lets sign-in work
    from a static export with no Node runtime and no `postMessage` channel.
    """
    client = _client(request, provider)
    return await client.authorize_redirect(request, _callback_url(request, provider))


@router.get("/callback/{provider}", name="oauth_callback")
async def oauth_callback(request: Request, provider: str):
    """Complete the exchange and act on the §5.1 decision."""
    profile = await _complete_exchange(request, provider)
    store = request.app.state.user_store

    session = await _session_user(request)
    linked = await store.lookup_identity(profile.provider, profile.subject)
    decision = decide(
        linked_user_id=linked,
        session_user_id=session.id if session else None,
        session_kind=session.kind if session else None,
        session_has_activity=(
            await store.has_activity(session.id)
            if session is not None and session.kind == "guest"
            else False
        ),
    )

    if decision.outcome is Outcome.CONFLICT:
        # Deliberately no cookie on this response: the guest keeps their
        # session until they say otherwise, and cancelling costs them nothing.
        token = request.app.state.claim_token.sign(session.id, decision.target_user_id)
        return RedirectResponse(f"/?claim=conflict&token={token}", status_code=307)

    if decision.outcome is Outcome.CREATE:
        target = await store.mint_guest()
        target_id = target.id
    else:
        target_id = decision.target_user_id

    if decision.outcome in (Outcome.PROMOTE, Outcome.CREATE):
        await store.promote(target_id, profile.email, profile.name, profile.avatar)
        await store.attach_identity(target_id, profile.provider, profile.subject, profile.email)

    response = RedirectResponse("/", status_code=307)
    set_session_cookie(request, response, request.app.state.session_cookie, target_id)
    return response


@router.get("/me")
async def me(user: CurrentUserDep, request: Request) -> dict:
    """Who the caller is. Mints a guest when there is none, like every other
    user-resolving route -- this is the call the frontend makes on mount, so
    it is where a first-time visitor's account comes from."""
    return {
        "id": user.id,
        "kind": user.kind,
        "email": user.email,
        "name": user.display_name,
        "avatar": user.avatar_url,
        "hasActivity": await request.app.state.user_store.has_activity(user.id),
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Drop the session cookie. The next request mints a fresh guest."""
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/claim")
async def claim(body: ClaimRequest, request: Request) -> Response:
    """Complete a contested sign-in the user has confirmed (§5.2)."""
    session = await _session_user(request)
    if session is None:
        raise ClaimTokenInvalidError("That confirmation is no longer valid.")

    target_id = request.app.state.claim_token.verify(body.token, session.id)
    if target_id is None:
        raise ClaimTokenInvalidError("That confirmation is no longer valid.")

    response = Response(status_code=200)
    set_session_cookie(request, response, request.app.state.session_cookie, target_id)
    return response


@router.get("/dev-login/{user_id}")
async def dev_login(request: Request, user_id: str):
    """Sign a session for an arbitrary user, with no provider involved.

    E2E only. This is unauthenticated session forgery: anyone who can reach it
    can become any user by guessing an id. It answers 404 rather than 403 when
    `AUTH_MOCK` is unset, so a deployment that has it switched off does not
    advertise that the route exists.
    """
    if not request.app.state.settings.auth_mock:
        raise AuthProviderUnavailableError("Not found.")

    user = await request.app.state.user_store.get(user_id)
    if user is None:
        raise AuthProviderUnavailableError("No such user.")

    response = RedirectResponse("/", status_code=307)
    set_session_cookie(request, response, request.app.state.session_cookie, user.id)
    return response
