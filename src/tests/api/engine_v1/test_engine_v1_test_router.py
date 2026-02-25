import pytest
from fastapi import FastAPI

from ii_agent.engine.v1.api.test import router as engine_test_router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/v1/test/agent/general"),
    ("POST", "/v1/test/agent/hitl"),
    ("POST", "/v1/test/agent/continue"),
    ("POST", "/v1/test/agent/session-summary"),
}


def _v1_app():
    app = FastAPI()
    app.include_router(engine_test_router, prefix="/v1")
    return app


def test_engine_v1_test_router_routes_registered():
    assert_routes_present(_v1_app(), EXPECTED_ROUTES)


def test_engine_v1_test_router_auth_contract():
    assert_auth_contract(_v1_app(), protected=EXPECTED_ROUTES)
