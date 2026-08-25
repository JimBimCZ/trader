"""Which providers this deployment offers, and how to talk to them.

Registering only the configured providers is what makes `oauth.create_client`
return None for the others -- so the router has one place to ask rather than
re-deriving the rule from settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from authlib.integrations.starlette_client import OAuth

from ..config import Settings

#: Display names for the sign-in sheet. Also the set of providers this app
#: knows how to normalise userinfo for -- adding a key here without adding a
#: branch to `normalize_profile` would produce a button that 502s.
PROVIDER_LABELS: dict[str, str] = {"google": "Google", "github": "GitHub"}


@dataclass(frozen=True)
class OAuthProfile:
    """One provider's answer, reduced to what this app stores.

    `subject` is the provider's own immutable id, and the only thing identity
    resolution matches on. Email is carried for display and never for lookup
    (D-6): cross-provider email matching is an account-takeover vector where a
    provider does not guarantee the address is verified.
    """

    provider: str
    subject: str
    email: str | None
    name: str | None
    avatar: str | None


def build_oauth(settings: Settings) -> OAuth:
    """An Authlib registry holding exactly the configured providers."""
    oauth = OAuth()
    configured = settings.configured_providers

    if "google" in configured:
        oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            # S256 is PKCE. Authlib stores the verifier in the Starlette
            # session cookie, which is why SessionMiddleware is mandatory --
            # see main.py.
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )

    if "github" in configured:
        oauth.register(
            name="github",
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            # `user:email` because GitHub omits a private address from /user;
            # without it a user whose email is hidden signs in with no email
            # at all, which is legal here but shows an empty account menu.
            client_kwargs={"scope": "read:user user:email"},
        )

    return oauth
