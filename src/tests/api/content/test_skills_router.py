import pytest

from ii_agent.settings.skills.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/user-settings/skills/github"),
    ("GET", "/user-settings/skills"),
    ("GET", "/user-settings/skills/{skill_id}"),
    ("PATCH", "/user-settings/skills/{skill_id}/toggle"),
    ("DELETE", "/user-settings/skills/{skill_id}"),
}


def test_skills_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_skills_router_auth_contract():
    assert_auth_contract(router, protected=EXPECTED_ROUTES)
