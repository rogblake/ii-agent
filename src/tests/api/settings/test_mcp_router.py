import pytest

from ii_agent.settings.mcp.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/user-settings/mcp/codex"),
    ("POST", "/user-settings/mcp/codex"),
    ("GET", "/user-settings/mcp/claude-code"),
    ("POST", "/user-settings/mcp/claude-code"),
    ("POST", "/user-settings/mcp"),
    ("GET", "/user-settings/mcp"),
    ("GET", "/user-settings/mcp/{setting_id}"),
    ("PUT", "/user-settings/mcp/{setting_id}"),
    ("DELETE", "/user-settings/mcp/{setting_id}"),
}


def test_mcp_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_mcp_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
