from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.exceptions import FileSizeLimitExceededError, FileUploadNotFoundError
from ii_agent.files.service import FileService


class FakeFileRepo:
    def __init__(self):
        self.created = []

    async def create(self, db, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(**kwargs)


class FakeSessionRepo:
    async def get_by_id(self, db, session_id):
        return None


@pytest.mark.asyncio
async def test_generate_upload_url_rejects_oversized_file(settings_factory):
    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        storage=MagicMock(),
        config=settings_factory(storage={"file_upload_size_limit": 10}),
    )

    with pytest.raises(FileSizeLimitExceededError):
        await service.generate_upload_url(
            db=None,
            user_id="u1",
            file_name="a.txt",
            content_type="text/plain",
            file_size=11,
        )


@pytest.mark.asyncio
async def test_complete_upload_creates_record_and_returns_signed_url(settings_factory):
    file_repo = FakeFileRepo()
    blob_name = "users/u1/uploads/f1-report.pdf"

    storage_mock = MagicMock()
    storage_mock.exists = AsyncMock(return_value=True)
    storage_mock.signed_url = AsyncMock(
        side_effect=lambda path, **kw: f"https://signed.local/{path}"
    )
    storage_mock.signed_upload_url = AsyncMock(
        side_effect=lambda path, ct, **kw: f"https://upload.local/{path}"
    )

    service = FileService(
        file_repo=file_repo,
        session_repo=FakeSessionRepo(),
        storage=storage_mock,
        config=settings_factory(),
    )

    response = await service.complete_upload(
        db=None,
        user_id="u1",
        file_id="f1",
        file_name="report.pdf",
        file_size=3,
        content_type="application/pdf",
        session_id="s1",
    )

    assert response.file_url.endswith(blob_name)
    assert file_repo.created[0]["storage_path"] == blob_name


@pytest.mark.asyncio
async def test_complete_upload_raises_when_object_missing(settings_factory):
    storage_mock = MagicMock()
    storage_mock.exists = AsyncMock(return_value=False)

    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        storage=storage_mock,
        config=settings_factory(),
    )

    with pytest.raises(FileUploadNotFoundError):
        await service.complete_upload(
            db=None,
            user_id="u1",
            file_id="missing",
            file_name="x.txt",
            file_size=1,
            content_type="text/plain",
            session_id=None,
        )
