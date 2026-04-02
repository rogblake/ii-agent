from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.service import FileService


class FakeFileRepo:
    async def get_by_user_and_paths(self, db, user_id, normalized_paths):
        return [SimpleNamespace(id="f1", storage_path=normalized_paths[0])]


class FakeSessionRepo:
    pass


class BrokenBatchStorage:
    async def signed_urls_batch(self, paths, **kw):
        raise RuntimeError("batch failed")

    async def signed_url(self, path, **kw):
        return f"https://signed.local/{path}"

    def public_url(self, path):
        return f"https://public.local/{path}"


@pytest.mark.asyncio
async def test_generate_download_urls_reports_missing_paths(settings_factory):
    storage_mock = MagicMock()
    storage_mock.signed_urls_batch = AsyncMock(
        side_effect=lambda paths, **kw: [f"https://signed.local/{p}" for p in paths]
    )
    storage_mock.public_url = MagicMock(side_effect=lambda p: f"https://public.local/{p}")

    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        storage=storage_mock,
        config=settings_factory(),
    )

    response = await service.generate_download_urls(
        db=None,
        user_id="u1",
        storage_paths=["/users/u1/file1.txt", "/users/u1/missing.txt"],
    )

    assert response.file_ids[0] == "f1"
    assert response.file_ids[1] is None
    assert response.missing_paths == ["users/u1/missing.txt"]


@pytest.mark.asyncio
async def test_signed_url_batch_falls_back_when_batch_signing_fails(settings_factory):
    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        storage=MagicMock(),
        config=settings_factory(),
    )
    service._storage = BrokenBatchStorage()

    file_uploads = [SimpleNamespace(storage_path="users/u1/file1.txt")]
    urls = await service._get_download_signed_urls_batch(file_uploads, force_signed=False)

    assert urls[0] == "https://signed.local/users/u1/file1.txt"


@pytest.mark.asyncio
async def test_signed_url_batch_force_signed_disables_permanent_fallback(settings_factory):
    class AlwaysFailStorage(BrokenBatchStorage):
        async def signed_url(self, path, **kw):
            raise RuntimeError("single-sign-fail")

    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        storage=MagicMock(),
        config=settings_factory(),
    )
    service._storage = AlwaysFailStorage()

    urls = await service._get_download_signed_urls_batch(
        [SimpleNamespace(storage_path="users/u1/file1.txt")],
        force_signed=True,
    )

    assert urls == [None]
