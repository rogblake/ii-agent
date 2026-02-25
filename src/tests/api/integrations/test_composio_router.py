import pytest

from ii_agent.integrations.connectors.composio.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/connectors/composio/toolkits"),
    ("GET", "/connectors/composio/profiles"),
    ("POST", "/connectors/composio/oauth-complete"),
    ("GET", "/connectors/composio/toolkits/{toolkit_slug}"),
    ("GET", "/connectors/composio/toolkits/{toolkit_slug}/actions"),
    ("POST", "/connectors/composio/{toolkit_slug}/connect"),
    ("GET", "/connectors/composio/{toolkit_slug}/status"),
    ("DELETE", "/connectors/composio/{toolkit_slug}"),
    ("GET", "/connectors/composio/profiles/{profile_id}/mcp-config"),
    ("POST", "/connectors/composio/profiles/{profile_id}/sync-to-agent"),
    ("DELETE", "/connectors/composio/profiles/{profile_id}"),
    ("POST", "/connectors/composio/profiles/{profile_id}/enable"),
    ("POST", "/connectors/composio/profiles/{profile_id}/disable"),
    ("PUT", "/connectors/composio/profiles/{profile_id}/tools"),
}


def test_composio_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_composio_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
