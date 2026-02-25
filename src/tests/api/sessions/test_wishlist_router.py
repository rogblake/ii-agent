import pytest

from ii_agent.sessions.wishlist.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/wishlist/sessions"),
    ("POST", "/wishlist/sessions/{session_id}"),
    ("DELETE", "/wishlist/sessions/{session_id}"),
}


def test_wishlist_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_wishlist_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
