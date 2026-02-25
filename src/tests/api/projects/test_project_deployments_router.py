import pytest
from fastapi import FastAPI

from ii_agent.projects.deployments.router import router as deployments_router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/project/{project_id}/deployment"),
}


def _project_app():
    app = FastAPI()
    app.include_router(deployments_router, prefix="/project")
    return app


def test_project_deployments_routes_registered():
    assert_routes_present(_project_app(), EXPECTED_ROUTES)


def test_project_deployments_auth_contract():
    assert_auth_contract(_project_app(), protected=EXPECTED_ROUTES)
