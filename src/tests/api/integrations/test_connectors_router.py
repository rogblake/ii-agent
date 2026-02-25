import pytest

from ii_agent.integrations.connectors.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/connectors/google-drive/auth-url"),
    ("POST", "/connectors/google-drive/callback"),
    ("GET", "/connectors/google-drive/status"),
    ("GET", "/connectors/google-drive/picker-config"),
    ("POST", "/connectors/google-drive/files"),
    ("DELETE", "/connectors/google-drive"),
    ("GET", "/connectors/github/auth-url"),
    ("POST", "/connectors/github/callback"),
    ("GET", "/connectors/github/status"),
    ("DELETE", "/connectors/github"),
    ("GET", "/connectors/github/app-config"),
    ("GET", "/connectors/github/repositories"),
}


def test_connectors_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_connectors_router_auth_contract():
    assert_auth_contract(
        router,
        protected=EXPECTED_ROUTES - {("GET", "/connectors/github/app-config")},
        public={("GET", "/connectors/github/app-config")},
    )
