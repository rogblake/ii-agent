from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.service import FileService


class FakeFileRepo:
    async def count_user_images(self, db, user_id):
        return 3

    async def get_user_images(self, db, user_id, limit, offset):
        return [
            SimpleNamespace(
                id="f1",
                file_name="generated.png",
                storage_path="sessions/s1/generated/img.png",
                created_at=datetime.now(timezone.utc),
                source="agent_generated",
            ),
            SimpleNamespace(
                id="f2",
                file_name="upload.png",
                storage_path="users/u1/uploads/img.png",
                created_at=datetime.now(timezone.utc),
                source="user_upload",
            ),
        ]


class FakeSessionRepo:
    pass


@pytest.mark.asyncio
async def test_media_library_pagination_and_source_classification(settings_factory):
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

    response = await service.get_media_library(
        db=None,
        user_id="u1",
        limit=2,
        offset=0,
    )

    assert response.total == 3
    assert response.limit == 2
    assert response.offset == 0
    assert response.has_more is True
    assert response.items[0].source == "generated"
    assert response.items[1].source == "upload"
