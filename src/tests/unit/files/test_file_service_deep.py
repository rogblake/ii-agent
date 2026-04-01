"""Deep unit tests for ii_agent.files.service covering remaining branches."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.files.exceptions import (
    FileAccessDeniedError,
    FileUploadNotFoundError,
    FileSizeLimitExceededError,
)
from ii_agent.files.service import FileService, IMAGE_CONTENT_TYPES


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_file(**kwargs):
    defaults = dict(
        id="file-1",
        file_name="test.txt",
        file_size=100,
        content_type="text/plain",
        storage_path="users/u1/uploads/file-1-test.txt",
        session_id="s-1",
        user_id="u-1",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class FakeFileRepo:
    def __init__(self):
        self.files: dict = {}
        self.session_updates = []

    async def get_by_id(self, db, file_id):
        return self.files.get(file_id)

    async def get_by_id_and_user(self, db, file_id, user_id):
        f = self.files.get(file_id)
        if f and f.user_id == user_id:
            return f
        return None

    async def get_by_session_and_id(self, db, session_id, file_id):
        f = self.files.get(file_id)
        if f and f.session_id == session_id:
            return f
        return None

    async def get_by_session_id(self, db, session_id):
        return [f for f in self.files.values() if f.session_id == session_id]

    async def create(self, db, **kwargs):
        # Map file_id -> id for consistency with the model attribute name
        f = SimpleNamespace(id=kwargs.get("file_id"), created_at=None, **kwargs)
        self.files[kwargs["file_id"]] = f
        return f

    async def update_session_id(self, db, file_id, session_id):
        f = self.files.get(file_id)
        if f:
            f.session_id = session_id
        self.session_updates.append((file_id, session_id))
        return bool(f)

    async def get_by_user_and_paths(self, db, user_id, paths):
        return [f for f in self.files.values() if f.storage_path in paths]

    async def count_user_images(self, db, user_id):
        return sum(1 for f in self.files.values() if f.content_type.startswith("image/"))

    async def get_user_images(self, db, user_id, limit, offset):
        imgs = [f for f in self.files.values() if f.content_type.startswith("image/")]
        return imgs[offset : offset + limit]


class FakeSessionRepo:
    def __init__(self):
        self.sessions: dict = {}

    async def get_by_id(self, db, session_id):
        return self.sessions.get(str(session_id))


def _make_storage_mock() -> MagicMock:
    """Create a mock with async StorageService-compatible interface."""
    storage = MagicMock()
    storage.signed_url = AsyncMock(side_effect=lambda path, **kw: f"signed://{path}")
    storage.signed_urls_batch = AsyncMock(
        side_effect=lambda paths, **kw: [f"signed://{p}" for p in paths]
    )
    storage.signed_upload_url = AsyncMock(
        side_effect=lambda path, ct, **kw: f"upload://{path}"
    )
    storage.exists = AsyncMock(return_value=False)
    storage.write = AsyncMock(return_value="path")
    storage.write_from_url = AsyncMock(side_effect=lambda url, path, ct=None: path)
    storage.read = AsyncMock(return_value=io.BytesIO(b""))
    storage.public_url = MagicMock(side_effect=lambda path: f"public://{path}")
    return storage


def _make_service(
    *,
    file_repo=None,
    session_repo=None,
    storage=None,
) -> FileService:
    config = SimpleNamespace(
        storage=SimpleNamespace(
            media_bucket_name="media-bucket",
            file_upload_bucket_name="uploads-bucket",
            file_upload_size_limit=1_000_000,
            signed_url_ttl_seconds=3600,
        )
    )
    if storage is None:
        storage = _make_storage_mock()
    return FileService(
        file_repo=file_repo or FakeFileRepo(),
        session_repo=session_repo or FakeSessionRepo(),
        storage=storage,
        config=config,
    )


# ---------------------------------------------------------------------------
# get_file_by_id
# ---------------------------------------------------------------------------


class TestGetFileById:
    @pytest.mark.asyncio
    async def test_raises_when_not_found(self):
        svc = _make_service()
        with pytest.raises(FileUploadNotFoundError):
            await svc.get_file_by_id(None, "non-existent")

    @pytest.mark.asyncio
    async def test_returns_file_data_when_found(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1")
        svc = _make_service(file_repo=repo)
        result = await svc.get_file_by_id(None, "f-1")
        assert result.id == "f-1"
        assert result.name == "test.txt"


# ---------------------------------------------------------------------------
# get_files_by_session_id
# ---------------------------------------------------------------------------


class TestGetFilesBySessionId:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_files(self):
        svc = _make_service()
        result = await svc.get_files_by_session_id(None, "s-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_files_for_session(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", session_id="s-1")
        repo.files["f-2"] = _make_file(id="f-2", session_id="s-2")
        svc = _make_service(file_repo=repo)
        result = await svc.get_files_by_session_id(None, "s-1")
        assert len(result) == 1
        assert result[0].id == "f-1"


# ---------------------------------------------------------------------------
# update_file_session_id
# ---------------------------------------------------------------------------


class TestUpdateFileSessionId:
    @pytest.mark.asyncio
    async def test_updates_session_id(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", session_id=None)
        svc = _make_service(file_repo=repo)
        result = await svc.update_file_session_id(None, "f-1", "s-new")
        assert result is True
        assert ("f-1", "s-new") in repo.session_updates


# ---------------------------------------------------------------------------
# create_file_record
# ---------------------------------------------------------------------------


class TestCreateFileRecord:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        svc = _make_service()
        from ii_agent.sessions.exceptions import SessionNotFoundError

        with pytest.raises(SessionNotFoundError):
            await svc.create_file_record(
                None,
                file_id="f-1",
                file_name="test.txt",
                file_size=100,
                storage_path="path",
                content_type="text/plain",
                session_id="no-session",
            )

    @pytest.mark.asyncio
    async def test_creates_file_record(self):
        session_repo = FakeSessionRepo()
        session = SimpleNamespace(id="s-1", user_id="u-1")
        session_repo.sessions["s-1"] = session
        svc = _make_service(session_repo=session_repo)
        result = await svc.create_file_record(
            None,
            file_id="f-new",
            file_name="new.txt",
            file_size=200,
            storage_path="users/u1/uploads/new.txt",
            content_type="text/plain",
            session_id="s-1",
        )
        assert result.file_id == "f-new"
        assert result.user_id == "u-1"


# ---------------------------------------------------------------------------
# write_file_from_url
# ---------------------------------------------------------------------------


class TestWriteFileFromUrl:
    @pytest.mark.asyncio
    async def test_resolves_user_from_session_when_not_provided(self):
        session_repo = FakeSessionRepo()
        session = SimpleNamespace(id="s-1", user_id="u-resolved")
        session_repo.sessions["s-1"] = session
        svc = _make_service(session_repo=session_repo)
        result = await svc.write_file_from_url(
            None,
            url="https://example.com/file.txt",
            file_name="file.txt",
            file_size=500,
            content_type="text/plain",
            session_id="s-1",
        )
        assert result.id is not None
        assert "file.txt" in result.name

    @pytest.mark.asyncio
    async def test_raises_when_session_not_found_and_no_user_id(self):
        svc = _make_service()
        from ii_agent.sessions.exceptions import SessionNotFoundError

        with pytest.raises(SessionNotFoundError):
            await svc.write_file_from_url(
                None,
                url="https://example.com/file.txt",
                file_name="file.txt",
                file_size=500,
                content_type="text/plain",
                session_id="no-session",
            )

    @pytest.mark.asyncio
    async def test_uses_provided_user_id(self):
        svc = _make_service()
        result = await svc.write_file_from_url(
            None,
            url="https://example.com/file.txt",
            file_name="file.txt",
            file_size=500,
            content_type="text/plain",
            session_id="s-1",
            user_id="u-explicit",
        )
        assert result.id is not None


# ---------------------------------------------------------------------------
# generate_upload_url
# ---------------------------------------------------------------------------


class TestGenerateUploadUrl:
    @pytest.mark.asyncio
    async def test_raises_when_size_exceeds_limit(self):
        svc = _make_service()
        with pytest.raises(FileSizeLimitExceededError):
            await svc.generate_upload_url(
                None,
                user_id="u-1",
                file_name="big.zip",
                content_type="application/zip",
                file_size=1_000_001,
            )

    @pytest.mark.asyncio
    async def test_returns_upload_url(self):
        svc = _make_service()
        result = await svc.generate_upload_url(
            None,
            user_id="u-1",
            file_name="photo.jpg",
            content_type="image/jpeg",
            file_size=500,
        )
        assert result.upload_url.startswith("upload://")
        assert result.id is not None


# ---------------------------------------------------------------------------
# complete_upload
# ---------------------------------------------------------------------------


class TestCompleteUpload:
    @pytest.mark.asyncio
    async def test_raises_when_blob_not_found(self):
        svc = _make_service()
        with pytest.raises(FileUploadNotFoundError):
            await svc.complete_upload(
                None,
                user_id="u-1",
                file_id="f-1",
                file_name="test.txt",
                file_size=100,
                content_type="text/plain",
                session_id=None,
            )

    @pytest.mark.asyncio
    async def test_returns_upload_complete_response(self):
        storage = _make_storage_mock()
        storage.exists = AsyncMock(return_value=True)
        svc = _make_service(storage=storage)
        result = await svc.complete_upload(
            None,
            user_id="u-1",
            file_id="f-done",
            file_name="done.txt",
            file_size=100,
            content_type="text/plain",
            session_id=None,
        )
        assert result.file_url.startswith("signed://")


# ---------------------------------------------------------------------------
# get_file_stream
# ---------------------------------------------------------------------------


class TestGetFileStream:
    @pytest.mark.asyncio
    async def test_raises_when_access_denied(self):
        svc = _make_service()
        with pytest.raises(FileAccessDeniedError):
            await svc.get_file_stream(None, "f-1", user_id="u-wrong")

    @pytest.mark.asyncio
    async def test_returns_streaming_response(self):
        from fastapi.responses import StreamingResponse

        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", user_id="u-1")
        svc = _make_service(file_repo=repo)
        result = await svc.get_file_stream(None, "f-1", user_id="u-1")
        assert isinstance(result, StreamingResponse)


# ---------------------------------------------------------------------------
# get_public_file_stream
# ---------------------------------------------------------------------------


class TestGetPublicFileStream:
    @pytest.mark.asyncio
    async def test_raises_when_not_found(self):
        svc = _make_service()
        with pytest.raises(FileUploadNotFoundError):
            await svc.get_public_file_stream(None, "s-1", "no-file")

    @pytest.mark.asyncio
    async def test_returns_streaming_response(self):
        from fastapi.responses import StreamingResponse

        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", session_id="s-1")
        svc = _make_service(file_repo=repo)
        result = await svc.get_public_file_stream(None, "s-1", "f-1")
        assert isinstance(result, StreamingResponse)


# ---------------------------------------------------------------------------
# upload_avatar
# ---------------------------------------------------------------------------


class TestUploadAvatar:
    @pytest.mark.asyncio
    async def test_uploads_and_returns_url(self):
        svc = _make_service()
        result = await svc.upload_avatar(
            None,
            user_id="u-1",
            file_content=b"image bytes",
            file_extension="jpg",
        )
        assert "u-1" in result


# ---------------------------------------------------------------------------
# get_avatar_url
# ---------------------------------------------------------------------------


class TestGetAvatarUrl:
    def test_returns_public_url(self):
        svc = _make_service()
        result = svc.get_avatar_url("users/u1/profile/avatar.jpg")
        assert result == "public://users/u1/profile/avatar.jpg"


# ---------------------------------------------------------------------------
# get_files_by_ids_and_update_session
# ---------------------------------------------------------------------------


class TestGetFilesByIdsAndUpdateSession:
    @pytest.mark.asyncio
    async def test_links_file_to_session(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", session_id=None)
        svc = _make_service(file_repo=repo)
        results = await svc.get_files_by_ids_and_update_session(
            None,
            file_ids=["f-1"],
            user_id="u-1",
            session_id="s-1",
        )
        assert len(results) == 1
        assert ("f-1", "s-1") in repo.session_updates

    @pytest.mark.asyncio
    async def test_skips_missing_files(self):
        svc = _make_service()
        results = await svc.get_files_by_ids_and_update_session(
            None,
            file_ids=["no-file"],
            user_id="u-1",
            session_id="s-1",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_does_not_update_if_already_linked_to_same_session(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", session_id="s-1")
        svc = _make_service(file_repo=repo)
        await svc.get_files_by_ids_and_update_session(
            None,
            file_ids=["f-1"],
            user_id="u-1",
            session_id="s-1",
        )
        # No update needed since already linked
        assert ("f-1", "s-1") not in repo.session_updates


# ---------------------------------------------------------------------------
# generate_download_urls
# ---------------------------------------------------------------------------


class TestGenerateDownloadUrls:
    @pytest.mark.asyncio
    async def test_returns_signed_urls_and_missing_paths(self):
        repo = FakeFileRepo()
        f = _make_file(id="f-1", storage_path="users/u1/uploads/test.txt")
        repo.files["f-1"] = f

        svc = _make_service(file_repo=repo)
        result = await svc.generate_download_urls(
            None,
            user_id="u-1",
            storage_paths=["users/u1/uploads/test.txt", "/missing/path.txt"],
        )
        assert len(result.signed_urls) == 2
        assert "missing/path.txt" in result.missing_paths

    @pytest.mark.asyncio
    async def test_normalizes_leading_slashes(self):
        repo = FakeFileRepo()
        f = _make_file(id="f-1", storage_path="users/u1/file.txt")
        repo.files["f-1"] = f

        svc = _make_service(file_repo=repo)
        result = await svc.generate_download_urls(
            None,
            user_id="u-1",
            storage_paths=["/users/u1/file.txt"],
        )
        # Should normalize the leading slash
        assert len(result.signed_urls) == 1


# ---------------------------------------------------------------------------
# get_media_library
# ---------------------------------------------------------------------------


class TestGetMediaLibrary:
    @pytest.mark.asyncio
    async def test_returns_items_with_signed_urls(self):
        repo = FakeFileRepo()
        from datetime import datetime, timezone

        repo.files["img-1"] = _make_file(
            id="img-1",
            content_type="image/png",
            storage_path="sessions/s1/img.png",
        )
        # Add created_at
        repo.files["img-1"].created_at = datetime.now(timezone.utc)

        svc = _make_service(file_repo=repo)
        result = await svc.get_media_library(
            None,
            user_id="u-1",
            limit=10,
            offset=0,
        )
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].url is not None

    @pytest.mark.asyncio
    async def test_has_more_flag(self):
        repo = FakeFileRepo()
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        for i in range(5):
            f = _make_file(
                id=f"img-{i}", content_type="image/jpeg", storage_path=f"sessions/s1/img{i}.jpg"
            )
            f.created_at = now
            repo.files[f"img-{i}"] = f

        svc = _make_service(file_repo=repo)
        result = await svc.get_media_library(
            None,
            user_id="u-1",
            limit=2,
            offset=0,
        )
        assert result.has_more is True
