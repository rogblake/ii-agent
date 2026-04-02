from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ii_agent.files.service import FileService


class FakeFileRepo:
    pass


class FakeSessionRepo:
    pass


@pytest.mark.asyncio
async def test_prepare_agent_files_splits_images_and_files(settings_factory, monkeypatch):
    service = FileService(
        file_repo=FakeFileRepo(),
        session_repo=FakeSessionRepo(),
        storage=MagicMock(),
        config=settings_factory(),
    )

    async def _fake_get_files(*args, **kwargs):
        return [
            SimpleNamespace(
                id="img-1",
                name="cat.png",
                content_type="image/png",
                url="https://signed.local/cat.png",
            ),
            SimpleNamespace(
                id="doc-1",
                name="doc.pdf",
                content_type="application/pdf",
                url="https://signed.local/doc.pdf",
            ),
            SimpleNamespace(
                id="skip-1",
                name="skip.txt",
                content_type="text/plain",
                url=None,
            ),
        ]

    monkeypatch.setattr(service, "get_files_by_ids_and_update_session", _fake_get_files)

    images, files = await service.prepare_agent_files(
        db=None,
        file_ids=["img-1", "doc-1", "skip-1"],
        user_id="u1",
        session_id="s1",
    )

    assert len(images) == 1
    assert images[0]["mime_type"] == "image/png"
    assert len(files) == 2
