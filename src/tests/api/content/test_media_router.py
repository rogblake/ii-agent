import pytest

from ii_agent.content.media.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/media-templates"),
    ("GET", "/media-templates/{template_id}"),
    ("GET", "/media-tools"),
    ("GET", "/media-tools/{tool_id}"),
    ("POST", "/media/reference-image"),
    ("GET", "/media/models/video"),
    ("GET", "/media/models/image"),
}


def test_media_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_media_router_auth_contract():
    assert_auth_contract(
        router,
        protected={("POST", "/media/reference-image")},
        public=EXPECTED_ROUTES - {("POST", "/media/reference-image")},
    )
