import pytest
from fastapi import FastAPI

from ii_agent.projects.secrets.router import router as secrets_router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/project/{session_id}/secrets"),
    ("POST", "/project/{session_id}/secrets"),
}


def _project_app():
    app = FastAPI()
    app.include_router(secrets_router, prefix="/project")
    return app


def test_project_secrets_routes_registered():
    assert_routes_present(_project_app(), EXPECTED_ROUTES)


def test_project_secrets_auth_contract():
    assert_auth_contract(_project_app(), protected=EXPECTED_ROUTES)
