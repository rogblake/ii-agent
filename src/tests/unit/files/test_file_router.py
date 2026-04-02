"""Unit tests for files router endpoints using FastAPI TestClient."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.auth.dependencies import get_current_user
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.middleware import ii_agent_error_handler
from ii_agent.files.dependencies import _get_file_service as get_file_service
from ii_agent.files.exceptions import FileAccessDeniedError
from ii_agent.files.router import router
from ii_agent.sessions.dependencies import get_session_repository

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = str(uuid.uuid4())
_SESSION_ID = str(uuid.uuid4())
_FILE_ID = str(uuid.uuid4())


def _make_user(user_id: str = _USER_ID) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email="test@example.com",
        is_active=True,
        avatar=None,
    )


def _make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        storage=SimpleNamespace(
            file_upload_size_limit=10 * 1024 * 1024,
            media_bucket_name="media-bucket",
            file_upload_bucket_name="upload-bucket",
        )
    )


def _make_file_service(
    *,
    upload_url_result=None,
    complete_result=None,
    stream_result=None,
    stream_side_effect=None,
    public_stream_result=None,
    download_urls_result=None,
    media_library_result=None,
    avatar_url: str = "https://example.com/avatar.jpg",
) -> MagicMock:
    svc = MagicMock()
    svc.generate_upload_url = AsyncMock(return_value=upload_url_result)
    svc.complete_upload = AsyncMock(return_value=complete_result)

    if stream_side_effect:
        svc.get_file_stream = AsyncMock(side_effect=stream_side_effect)
    else:
        svc.get_file_stream = AsyncMock(return_value=stream_result)

    svc.get_public_file_stream = AsyncMock(return_value=public_stream_result)
    svc.generate_download_urls = AsyncMock(return_value=download_urls_result)
    svc.get_media_library = AsyncMock(return_value=media_library_result)
    svc.upload_avatar = AsyncMock(return_value=avatar_url)
    svc.get_avatar_url = MagicMock(return_value=avatar_url)
    return svc


def _make_session_repo(*, session=None) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=session)
    repo.get_public_by_id = AsyncMock(return_value=session)
    return repo


def _build_app(
    file_service: MagicMock,
    session_repo: MagicMock | None = None,
    user: SimpleNamespace | None = None,
    settings: SimpleNamespace | None = None,
) -> FastAPI:
    from ii_agent.core.config.settings import get_settings

    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)

    _user = user or _make_user()
    _session_repo = session_repo or _make_session_repo()
    _settings = settings or _make_settings()

    app.dependency_overrides[get_current_user] = lambda: _user
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: file_service
    app.dependency_overrides[get_session_repository] = lambda: _session_repo

    app.dependency_overrides[get_settings] = lambda: _settings

    return app


# ---------------------------------------------------------------------------
# Tests – POST /chat/generate-upload-url
# ---------------------------------------------------------------------------


def test_generate_upload_url_success():
    """Arrange: valid file info; Act: POST generate-upload-url; Assert: signed URL returned."""
    upload_result = SimpleNamespace(
        id=_FILE_ID,
        upload_url="https://upload.example.com/signed",
        model_dump=lambda: {"id": _FILE_ID, "upload_url": "https://upload.example.com/signed"},
    )
    svc = _make_file_service(upload_url_result=upload_result)

    from ii_agent.files.schemas import GenerateUploadUrlResponse

    upload_result2 = GenerateUploadUrlResponse(
        id=_FILE_ID,
        upload_url="https://upload.example.com/signed",
    )
    svc.generate_upload_url = AsyncMock(return_value=upload_result2)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.post(
        "/chat/generate-upload-url",
        json={
            "file_name": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == _FILE_ID
    assert "upload_url" in data


def test_generate_upload_url_calls_service_with_correct_params():
    """Assert: service is called with all required params."""
    from ii_agent.files.schemas import GenerateUploadUrlResponse

    result = GenerateUploadUrlResponse(id=_FILE_ID, upload_url="https://upload.local")
    svc = _make_file_service()
    svc.generate_upload_url = AsyncMock(return_value=result)

    app = _build_app(svc)
    client = TestClient(app)
    client.post(
        "/chat/generate-upload-url",
        json={
            "file_name": "report.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "file_size": 2048,
        },
    )

    svc.generate_upload_url.assert_called_once()
    call_kwargs = svc.generate_upload_url.call_args.kwargs
    assert call_kwargs["file_name"] == "report.xlsx"
    assert call_kwargs["file_size"] == 2048


# ---------------------------------------------------------------------------
# Tests – POST /chat/upload-complete
# ---------------------------------------------------------------------------


def test_upload_complete_with_session_success():
    """Arrange: session owned by user; Act: POST upload-complete; Assert: file URL returned."""
    user = _make_user()
    session = SimpleNamespace(id=_SESSION_ID, user_id=user.id)
    session_repo = _make_session_repo(session=session)

    from ii_agent.files.schemas import UploadCompleteResponse

    result = UploadCompleteResponse(file_url="https://files.example.com/test.pdf")
    svc = _make_file_service(complete_result=result)

    app = _build_app(svc, session_repo=session_repo, user=user)
    client = TestClient(app)
    resp = client.post(
        "/chat/upload-complete",
        json={
            "id": _FILE_ID,
            "file_name": "test.pdf",
            "file_size": 1024,
            "content_type": "application/pdf",
            "session_id": _SESSION_ID,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "file_url" in data


def test_upload_complete_session_not_owned_by_user():
    """Arrange: session owned by different user; Assert: 404."""
    user = _make_user()
    other_user_session = SimpleNamespace(id=_SESSION_ID, user_id="other-user")
    session_repo = _make_session_repo(session=other_user_session)
    svc = _make_file_service()

    app = _build_app(svc, session_repo=session_repo, user=user)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/chat/upload-complete",
        json={
            "id": _FILE_ID,
            "file_name": "test.pdf",
            "file_size": 1024,
            "content_type": "application/pdf",
            "session_id": _SESSION_ID,
        },
    )

    assert resp.status_code == 404


def test_upload_complete_without_session():
    """Arrange: no session_id; Act: POST upload-complete; Assert: 200 without session check."""
    from ii_agent.files.schemas import UploadCompleteResponse

    result = UploadCompleteResponse(file_url="https://files.example.com/test.pdf")
    svc = _make_file_service(complete_result=result)
    session_repo = _make_session_repo()

    app = _build_app(svc, session_repo=session_repo)
    client = TestClient(app)
    resp = client.post(
        "/chat/upload-complete",
        json={
            "id": _FILE_ID,
            "file_name": "test.pdf",
            "file_size": 1024,
            "content_type": "application/pdf",
        },
    )

    assert resp.status_code == 200
    session_repo.get_by_id.assert_not_called()


# ---------------------------------------------------------------------------
# Tests – GET /chat/files/{file_id}
# ---------------------------------------------------------------------------


def test_download_file_success():
    """Arrange: file exists and owned; Act: GET file; Assert: stream returned."""
    from fastapi.responses import StreamingResponse

    async def _stream():
        yield b"file content"

    stream_resp = StreamingResponse(_stream(), media_type="application/pdf")
    svc = _make_file_service(stream_result=stream_resp)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.get(f"/chat/files/{_FILE_ID}")

    assert resp.status_code == 200


def test_download_file_access_denied_returns_404():
    """Arrange: file access denied; Assert: 404."""
    svc = _make_file_service(stream_side_effect=FileAccessDeniedError(_FILE_ID))

    app = _build_app(svc)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(f"/chat/files/{_FILE_ID}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests – GET /public/chat/{session_id}/files/{file_id}
# ---------------------------------------------------------------------------


def test_download_public_file_success():
    """Arrange: public session with file; Act: GET public file; Assert: 200."""
    from fastapi.responses import StreamingResponse

    async def _stream():
        yield b"public file content"

    session = SimpleNamespace(id=_SESSION_ID, user_id=_USER_ID)
    session_repo = _make_session_repo(session=session)
    stream_resp = StreamingResponse(_stream(), media_type="image/png")
    svc = _make_file_service(public_stream_result=stream_resp)

    # Public endpoint; no auth override needed
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: svc
    app.dependency_overrides[get_session_repository] = lambda: session_repo

    client = TestClient(app)
    resp = client.get(f"/public/chat/{_SESSION_ID}/files/{_FILE_ID}")

    assert resp.status_code == 200


def test_download_public_file_session_not_found():
    """Arrange: session not public; Assert: 404."""
    session_repo = _make_session_repo(session=None)
    svc = _make_file_service()

    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(IIAgentError, ii_agent_error_handler)
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()
    app.dependency_overrides[get_file_service] = lambda: svc
    app.dependency_overrides[get_session_repository] = lambda: session_repo

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(f"/public/chat/{_SESSION_ID}/files/{_FILE_ID}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests – POST /chat/files/download-urls
# ---------------------------------------------------------------------------


def test_generate_download_urls_success():
    """Arrange: valid paths; Act: POST download-urls; Assert: signed URLs returned."""
    from ii_agent.files.schemas import GenerateDownloadUrlsResponse

    result = GenerateDownloadUrlsResponse(
        signed_urls=["https://signed.example.com/file1", None],
        missing_paths=[],
        file_ids=[_FILE_ID, None],
    )
    svc = _make_file_service(download_urls_result=result)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.post(
        "/chat/files/download-urls",
        json={"storage_paths": ["path/to/file1.pdf", "path/to/file2.png"]},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["signed_urls"]) == 2


def test_generate_download_urls_empty_paths_returns_400():
    """Arrange: empty paths list; Assert: 400 validation error."""
    svc = _make_file_service()

    app = _build_app(svc)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/chat/files/download-urls",
        json={"storage_paths": []},
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Tests – GET /chat/user-media-library
# ---------------------------------------------------------------------------


def test_list_user_media_library_success():
    """Arrange: user with media; Act: GET media library; Assert: items returned."""
    from ii_agent.files.schemas import MediaLibraryResponse, MediaLibraryItem

    items = [
        MediaLibraryItem(
            id=_FILE_ID,
            name="photo.jpg",
            url="https://example.com/photo.jpg",
            source="upload",
            created_at=datetime.now(timezone.utc),
        )
    ]
    result = MediaLibraryResponse(
        items=items,
        total=1,
        limit=12,
        offset=0,
        has_more=False,
    )
    svc = _make_file_service(media_library_result=result)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.get("/chat/user-media-library")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_list_user_media_library_with_pagination():
    """Arrange: pagination params; Assert: service called with limit and offset."""
    from ii_agent.files.schemas import MediaLibraryResponse

    result = MediaLibraryResponse(items=[], total=0, limit=5, offset=10, has_more=False)
    svc = _make_file_service(media_library_result=result)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.get("/chat/user-media-library?limit=5&offset=10")

    assert resp.status_code == 200
    call_kwargs = svc.get_media_library.call_args.kwargs
    assert call_kwargs["limit"] == 5
    assert call_kwargs["offset"] == 10


def test_list_user_media_library_empty():
    """Arrange: no media; Assert: empty items list."""
    from ii_agent.files.schemas import MediaLibraryResponse

    result = MediaLibraryResponse(items=[], total=0, limit=12, offset=0, has_more=False)
    svc = _make_file_service(media_library_result=result)

    app = _build_app(svc)
    client = TestClient(app)
    resp = client.get("/chat/user-media-library")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# Tests – GET /avatar
# ---------------------------------------------------------------------------


def test_get_avatar_success():
    """Arrange: user with avatar; Act: GET avatar; Assert: URL returned."""
    user = _make_user()
    user.avatar = f"users/{_USER_ID}/profile/avatar.png"
    avatar_url = "https://example.com/avatar.png"
    svc = _make_file_service(avatar_url=avatar_url)

    app = _build_app(svc, user=user)
    client = TestClient(app)
    resp = client.get("/avatar")

    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == avatar_url


def test_get_avatar_not_found():
    """Arrange: user with no avatar; Assert: 404."""
    user = _make_user()
    user.avatar = None
    svc = _make_file_service()

    app = _build_app(svc, user=user)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/avatar")

    assert resp.status_code == 404
