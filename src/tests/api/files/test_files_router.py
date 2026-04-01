import pytest

from ii_agent.files.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/assets/upload"),
    ("POST", "/assets/{asset_id}/complete"),
    ("GET", "/assets/{asset_id}/download"),
    ("POST", "/assets/download-urls"),
    ("GET", "/assets/media-library"),
    ("POST", "/assets/avatar"),
    ("GET", "/assets/avatar"),
}


def test_files_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_files_router_auth_contract():
    assert_auth_contract(
        router,
        protected=EXPECTED_ROUTES,
    )
