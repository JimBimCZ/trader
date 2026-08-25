"""Which providers exist, and the rule that keeps the quick start zero-config."""

from __future__ import annotations

import dataclasses

import pytest

from app.auth.providers import PROVIDER_LABELS, build_oauth
from app.config import Settings


def _settings(**overrides) -> Settings:
    return dataclasses.replace(Settings(database_url="postgresql://x/y"), **overrides)


class TestConfiguredProviders:
    def test_none_configured_is_the_default(self):
        """The zero-config quick start: no credentials, no sign-in, guest only."""
        assert _settings().configured_providers == ()

    def test_a_provider_needs_both_halves(self):
        """An id with no secret cannot complete an exchange, so offering the
        button would produce a dead end rather than a sign-in."""
        assert _settings(google_client_id="id").configured_providers == ()
        assert _settings(google_client_secret="secret").configured_providers == ()

    def test_both_halves_configure_it(self):
        settings = _settings(google_client_id="id", google_client_secret="secret")
        assert settings.configured_providers == ("google",)

    def test_order_is_stable(self):
        """The UI renders them in this order; a set would reshuffle the sheet
        between deployments."""
        settings = _settings(
            github_client_id="i",
            github_client_secret="s",
            google_client_id="i",
            google_client_secret="s",
        )
        assert settings.configured_providers == ("google", "github")

    @pytest.mark.parametrize("provider", ["google", "github"])
    def test_every_provider_has_a_label(self, provider):
        assert PROVIDER_LABELS[provider]


class TestRegistry:
    def test_only_configured_providers_are_registered(self):
        oauth = build_oauth(_settings(google_client_id="id", google_client_secret="secret"))
        assert oauth.create_client("google") is not None
        assert oauth.create_client("github") is None
