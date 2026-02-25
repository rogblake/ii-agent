import pytest

from ii_agent.files.router import router
from tests.api.contracts import assert_auth_contract, assert_routes_present

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
    ("POST", "/chat/generate-upload-url"),
    ("POST", "/chat/upload-complete"),
    ("GET", "/chat/files/{file_id}"),
    ("GET", "/public/chat/{session_id}/files/{file_id}"),
    ("POST", "/chat/files/download-urls"),
    ("GET", "/chat/user-media-library"),
    ("POST", "/avatar"),
    ("GET", "/avatar"),
}


def test_files_router_routes_registered():
    assert_routes_present(router, EXPECTED_ROUTES)


def test_files_router_auth_contract():
    assert_auth_contract(
        router,
        protected=EXPECTED_ROUTES - {("GET", "/public/chat/{session_id}/files/{file_id}")},
        public={("GET", "/public/chat/{session_id}/files/{file_id}")},
    )
