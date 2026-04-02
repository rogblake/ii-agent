from types import SimpleNamespace

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
async def test_generate_upload_url_rejects_oversized_file(settings_factory, in_memory_storage):
    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        file_store=in_memory_storage,
        media_store=None,
        config=settings_factory(),
    )

    with pytest.raises(FileSizeLimitExceededError):
        await service.generate_upload_url(
            db=None,
            user_id="u1",
            file_name="a.txt",
            content_type="text/plain",
            file_size=11,
            upload_storage=in_memory_storage,
            max_file_size=10,
        )


@pytest.mark.asyncio
async def test_complete_upload_creates_record_and_returns_signed_url(settings_factory, in_memory_storage):
    file_repo = FakeFileRepo()
    service = FileService(
        file_repo=file_repo,
        session_repo=FakeSessionRepo(),
        file_store=in_memory_storage,
        media_store=None,
        config=settings_factory(),
    )

    blob_name = "users/u1/uploads/f1-report.pdf"
    in_memory_storage.write(b"pdf", blob_name)

    response = await service.complete_upload(
        db=None,
        user_id="u1",
        file_id="f1",
        file_name="report.pdf",
        file_size=3,
        content_type="application/pdf",
        session_id="s1",
        upload_storage=in_memory_storage,
    )

    assert response.file_url.endswith(blob_name)
    assert file_repo.created[0]["storage_path"] == blob_name


@pytest.mark.asyncio
async def test_complete_upload_raises_when_object_missing(settings_factory, in_memory_storage):
    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        file_store=in_memory_storage,
        media_store=None,
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
            upload_storage=in_memory_storage,
        )
