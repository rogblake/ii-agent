import pytest

from ii_agent.content.slides.templates.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/slide-templates"),
    ("GET", "/slide-templates/{template_id}"),
    ("POST", "/slide-templates"),
}


def test_slide_templates_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_slide_templates_router_auth_contract():
    assert_auth_contract(
        router,
        protected={("POST", "/slide-templates")},
        public={
            ("GET", "/slide-templates"),
            ("GET", "/slide-templates/{template_id}"),
        },
    )
