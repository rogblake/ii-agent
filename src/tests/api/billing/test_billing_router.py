import pytest

from ii_agent.billing.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/billing/checkout-session"),
    ("POST", "/billing/webhook"),
    ("POST", "/billing/portal-session"),
}


def test_billing_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_billing_router_auth_contract():
    assert_auth_contract(
        router,
        protected={
            ("POST", "/billing/checkout-session"),
            ("POST", "/billing/portal-session"),
        },
        public={("POST", "/billing/webhook")},
    )
