import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.exceptions import FileAccessDeniedError, FileUploadNotFoundError
from ii_agent.files.service import FileService


class FakeFileRepo:
    def __init__(self, file_record=None):
        self.file_record = file_record

    async def get_by_id_and_user(self, db, file_id, user_id):
        return self.file_record

    async def get_by_session_and_id(self, db, session_id, file_id):
        return self.file_record


class FakeSessionRepo:
    pass


@pytest.mark.asyncio
async def test_get_file_stream_denies_non_owner(settings_factory):
    service = FileService(
        file_repo=FakeFileRepo(file_record=None),
        session_repo=FakeSessionRepo(),
        storage=MagicMock(),
        config=settings_factory(),
    )

    with pytest.raises(FileAccessDeniedError):
        await service.get_file_stream(None, "f1", user_id="u1")


@pytest.mark.asyncio
async def test_get_public_file_stream_requires_file(settings_factory):
    service = FileService(
        file_repo=FakeFileRepo(file_record=None),
        session_repo=FakeSessionRepo(),
        storage=MagicMock(),
        config=settings_factory(),
    )

    with pytest.raises(FileUploadNotFoundError):
        await service.get_public_file_stream(None, "s1", "f1")


@pytest.mark.asyncio
async def test_get_file_stream_returns_streaming_response(settings_factory):
    path = "users/u1/uploads/f1-file.txt"
    file_record = SimpleNamespace(
        id="f1",
        file_name="file.txt",
        file_size=11,
        content_type="text/plain",
        storage_path=path,
    )

    storage_mock = MagicMock()
    storage_mock.read = AsyncMock(return_value=io.BytesIO(b"hello world"))

    service = FileService(
        file_repo=FakeFileRepo(file_record=file_record),
        session_repo=FakeSessionRepo(),
        storage=storage_mock,
        config=settings_factory(),
    )

    response = await service.get_file_stream(None, "f1", user_id="u1")

    assert response.headers["Content-Length"] == "11"
    assert "attachment" in response.headers["Content-Disposition"]
