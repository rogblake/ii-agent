import pytest

from ii_agent.projects.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/project/{session_id}"),
}


def test_project_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_project_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
