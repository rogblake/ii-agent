from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.auth.dependencies import get_current_user
from ii_agent.auth.users.dependencies import get_user_service
from ii_agent.billing.credits.dependencies import get_credit_service
from ii_agent.content.storybook.dependencies import (
    get_storybook_ai_edit_service,
    get_storybook_edit_service,
    get_storybook_export_service,
    get_storybook_service,
    get_storybook_voice_service,
)
from ii_agent.content.storybook.router import router
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.llm.dependencies import get_llm_execution_service
from ii_agent.core.middleware import ii_agent_error_handler
from ii_agent.core.exceptions import IIAgentError, ValidationError
from ii_agent.core.storage.dependencies import get_media_template_storage
from ii_agent.sessions.dependencies import get_session_service
from ii_agent.settings.llm.dependencies import get_llm_setting_service


pytestmark = pytest.mark.unit


def _make_app(*, session_access: bool = True, export_bytes: bytes | None = b"pdf"):
    app = FastAPI()
    app.include_router(router)
    app.exception_handler(IIAgentError)(ii_agent_error_handler)

    storybook = SimpleNamespace(
        id="sb1",
        session_id="session-1",
        name="My Story",
    )
    storybook_detail = SimpleNamespace(
        **storybook.__dict__,
        pages=[],
    )

    class _StorybookService:
        async def get_storybook_detail(self, db, storybook_id: str, include_pages: bool):
            return storybook_detail if storybook_id == "sb1" else None

        async def get_session_storybooks(self, db, session_id: str, include_pages: bool):
            return {"session_id": session_id, "storybooks": [], "total": 0}

        def build_generation_response(self, _storybook):
            return {"type": "storybook_progress", "storybook_id": "sb1"}

    class _SessionService:
        async def get_session_details(self, db, session_id: str, user_id: str):
            return {"id": session_id} if session_access else None

        async def get_public_session_details(self, db, session_id: str):
            return {"id": session_id}

    class _EditService:
        async def save_all_page_edits_with_billing(
            self, db, *, storybook_id, user_id, page_changes, image_urls
        ):
            return storybook_detail

        async def get_version_history(self, db, storybook_id):
            return []

    class _AIEditService:
        async def rewrite_content(
            self, db, *, storybook, user_id: str, content: str, page_image_url=None
        ):
            if not content.strip():
                raise ValidationError("No content provided to rewrite")
            return "rewritten text"

        async def generate_background(
            self,
            db,
            *,
            storybook,
            user_id: str,
            prompt: str,
            page_image_url=None,
            text_position=None,
        ):
            if not prompt.strip():
                raise ValidationError("No prompt provided for image generation")
            return "https://storage.local/generated-background.png"

        async def regenerate_image(
            self,
            db,
            *,
            storybook,
            user_id: str,
            page_number: int,
            prompt: str,
            reference_image_url=None,
            scene_text=None,
            text_position=None,
            text_percentage=None,
        ):
            if not prompt.strip():
                raise ValidationError("No prompt provided for image regeneration")
            return "https://storage.local/generated-page.png"

    class _ExportService:
        async def download_storybook_as_pdf(self, db, storybook_id: str):
            return export_bytes

        async def download_storybook_page_as_pdf(self, db, storybook_id: str, page_number: int):
            return export_bytes if page_number == 1 else None

    class _CreditService:
        async def require_billing_ok(self, db, user_id: str):
            return None

    class _VoiceService:
        def get_generation_status(self, storybook):
            return "completed"

        async def cancel_generation(self, db, storybook_id):
            return None

    class _Storage:
        def upload_and_get_permanent_url(
            self, file_obj, path: str, content_type: str | None = None
        ):
            return f"https://storage.local/{path}"

    async def _fake_db():
        yield SimpleNamespace(rollback=AsyncMock())

    async def _fake_user():
        return SimpleNamespace(id="user-1")

    app.dependency_overrides[_db_session_dependency] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_storybook_service] = lambda: _StorybookService()
    app.dependency_overrides[get_storybook_edit_service] = lambda: _EditService()
    app.dependency_overrides[get_storybook_ai_edit_service] = lambda: _AIEditService()
    app.dependency_overrides[get_storybook_export_service] = lambda: _ExportService()
    app.dependency_overrides[get_storybook_voice_service] = lambda: _VoiceService()
    app.dependency_overrides[get_credit_service] = lambda: _CreditService()
    app.dependency_overrides[get_session_service] = lambda: _SessionService()
    app.dependency_overrides[get_user_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_llm_setting_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_llm_execution_service] = lambda: SimpleNamespace()
    app.dependency_overrides[get_media_template_storage] = lambda: _Storage()
    return app


def test_storybook_edit_save_requires_auth_header():
    app = _make_app()
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        resp = client.post(
            "/storybooks/sb1/edit/save",
            json={"storybook_id": "sb1", "page_changes": []},
        )

    assert resp.status_code == 403


def test_storybook_edit_save_path_validation_error_response():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/storybooks/sb1/edit/save",
            headers={"Authorization": "Bearer token"},
            json={
                "storybook_id": "sb2",
                "page_changes": [{"page_number": 1, "changes": []}],
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "storybook": None,
        "error": "Path storybook_id does not match request.storybook_id",
    }


def test_storybook_ai_rewrite_path_validation_error_response():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/storybooks/sb1/edit/ai-rewrite",
            headers={"Authorization": "Bearer token"},
            json={
                "storybook_id": "sb2",
                "content": "Rewrite me",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "rewritten_content": None,
        "error": "Path storybook_id does not match request.storybook_id",
    }


def test_storybook_ai_regenerate_requires_prompt():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/storybooks/sb1/edit/ai-regenerate-image",
            headers={"Authorization": "Bearer token"},
            json={
                "storybook_id": "sb1",
                "page_number": 1,
                "prompt": "   ",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "image_url": None,
        "error": "No prompt provided for image regeneration",
    }


def test_storybook_upload_background_rejects_non_image():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/storybooks/sb1/edit/upload-background",
            headers={"Authorization": "Bearer token"},
            files={"file": ("notes.txt", BytesIO(b"text"), "text/plain")},
        )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"] == "validation"
    assert "Only image uploads are supported" in payload["detail"]


def test_storybook_download_export_failure_and_access_denied():
    app_export_fail = _make_app(export_bytes=None)
    with TestClient(app_export_fail) as client:
        resp = client.get(
            "/storybooks/sb1/download",
            headers={"Authorization": "Bearer token"},
        )
    assert resp.status_code == 500
    assert resp.json()["error"] == "storybook_export"

    app_access_denied = _make_app(session_access=False)
    with TestClient(app_access_denied) as client:
        resp = client.get(
            "/storybooks/sb1/download",
            headers={"Authorization": "Bearer token"},
        )
    assert resp.status_code == 403
    assert resp.json()["error"] == "storybook_access_denied"


def test_storybook_not_found_and_page_not_found_errors():
    app = _make_app()
    with TestClient(app) as client:
        not_found = client.get(
            "/storybooks/unknown",
            headers={"Authorization": "Bearer token"},
        )
        assert not_found.status_code == 404
        assert not_found.json()["error"] == "storybook_not_found"

        page_missing = client.get(
            "/storybooks/sb1/download/page/2",
            headers={"Authorization": "Bearer token"},
        )
        assert page_missing.status_code == 404
        assert page_missing.json()["error"] == "storybook_page_not_found"


def test_storybook_session_list_and_cancel_endpoint():
    app = _make_app()
    with TestClient(app) as client:
        listing = client.get(
            "/storybooks/session/session-1?include_pages=true",
            headers={"Authorization": "Bearer token"},
        )
        assert listing.status_code == 200
        assert listing.json()["session_id"] == "session-1"

        cancelled = client.post(
            "/storybooks/sb1/cancel",
            headers={"Authorization": "Bearer token"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["success"] is False
