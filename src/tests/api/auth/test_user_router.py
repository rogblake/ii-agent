import pytest

from ii_agent.auth.users.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("PATCH", "/auth/me/language"),
    ("DELETE", "/auth/me"),
}


def test_user_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_user_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
