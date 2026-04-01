from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.service import FileService

pytestmark = pytest.mark.integration


class FileRepo:
    def __init__(self):
        self.created = {}

    async def create(self, db, **kwargs):
        file_obj = SimpleNamespace(id=kwargs["file_id"], **kwargs)
        self.created[kwargs["storage_path"]] = file_obj
        return file_obj

    async def get_by_user_and_paths(self, db, user_id, normalized_paths):
        return [self.created[p] for p in normalized_paths if p in self.created]


class SessionRepo:
    async def get_by_id(self, db, session_id):
        return SimpleNamespace(user_id="u1")


@pytest.mark.asyncio
async def test_file_upload_lifecycle_integration(settings_factory):
    repo = FileRepo()

    storage_mock = MagicMock()
    storage_mock.signed_upload_url = AsyncMock(
        side_effect=lambda path, ct, **kw: f"https://upload.local/{path}"
    )
    storage_mock.exists = AsyncMock(return_value=True)
    storage_mock.signed_url = AsyncMock(
        side_effect=lambda path, **kw: f"https://signed.local/{path}"
    )
    storage_mock.signed_urls_batch = AsyncMock(
        side_effect=lambda paths, **kw: [f"https://signed.local/{p}" for p in paths]
    )
    storage_mock.public_url = MagicMock(
        side_effect=lambda p: f"https://public.local/{p}"
    )

    service = FileService(
        file_repo=repo,
        session_repo=SessionRepo(),
        storage=storage_mock,
        config=settings_factory(storage={"file_upload_size_limit": 10}),
    )

    upload = await service.generate_upload_url(
        db=None,
        user_id="u1",
        file_name="a.txt",
        content_type="text/plain",
        file_size=3,
    )

    blob = f"users/u1/uploads/{upload.id}-a.txt"

    completed = await service.complete_upload(
        db=None,
        user_id="u1",
        file_id=upload.id,
        file_name="a.txt",
        file_size=3,
        content_type="text/plain",
        session_id="s1",
    )

    downloads = await service.generate_download_urls(
        db=None,
        user_id="u1",
        storage_paths=[blob, "users/u1/uploads/missing.txt"],
    )

    assert completed.file_url.endswith(blob)
    assert downloads.signed_urls[0].endswith(blob)
    assert downloads.missing_paths == ["users/u1/uploads/missing.txt"]
