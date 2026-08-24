"""Guards on docker-compose.yml that the app cannot enforce at runtime.

`DATABASE_URL` is required with no fallback, which makes the app's
availability depend on the database container's -- a coupling that did not
exist when the database was a bind-mounted file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture(scope="module")
def services() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]


class TestRestartPolicies:
    def test_the_database_restarts_with_the_app(self, services):
        """`depends_on` is honoured by `compose up`, not by the daemon on
        reboot. With a policy on the app but not the database, a host restart
        brings the app back against a stopped database -- and since
        DATABASE_URL is required, it crash-loops until someone runs compose
        by hand."""
        assert services["postgres"].get("restart") == services["trader"].get("restart")

    @pytest.mark.parametrize("service", ["postgres", "trader"])
    def test_every_service_declares_one(self, services, service):
        assert services[service].get("restart"), f"{service} has no restart policy"


class TestExposure:
    @pytest.mark.parametrize("service", ["postgres", "trader"])
    def test_ports_are_bound_to_localhost_only(self, services, service):
        """The app has no auth and executes trades without confirmation; the
        database's password is 'trader'. Neither may reach the LAN."""
        for mapping in services[service].get("ports", []):
            assert str(mapping).startswith("127.0.0.1:"), (
                f"{service} publishes {mapping} on all interfaces"
            )
