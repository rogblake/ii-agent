import pytest

from ii_agent.projects.subdomains.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/subdomains/check-availability"),
    ("POST", "/subdomains/claim"),
    ("GET", "/subdomains/reserved"),
    ("GET", "/subdomains/base-domain/info"),
    ("GET", "/subdomains/{subdomain}"),
    ("DELETE", "/subdomains/{subdomain}"),
}


def test_subdomains_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_subdomains_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
