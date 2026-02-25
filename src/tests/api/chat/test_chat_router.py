import pytest

from ii_agent.chat.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("GET", "/v1/chat/conversations/{session_id}/advanced-mode"),
    ("POST", "/v1/chat/conversations/{session_id}/advanced-mode"),
    ("POST", "/v1/chat/conversations"),
    ("POST", "/v1/chat/conversations/{session_id}/stop"),
    ("GET", "/v1/chat/conversations/{session_id}"),
    ("GET", "/v1/chat/conversations/{session_id}/public"),
    ("DELETE", "/v1/chat/conversation/{session_id}"),
}


def test_chat_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_chat_router_auth_contract():
    assert_auth_contract(
        router,
        protected=EXPECTED_ROUTES - {("GET", "/v1/chat/conversations/{session_id}/public")},
        public={("GET", "/v1/chat/conversations/{session_id}/public")},
    )
