from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.content.media.constants import IMAGE_MINI_TOOLS_TYPE
from ii_agent.content.media.service import MediaTemplateService, _map_template_to_media_tool


class FakeMediaTemplateRepo:
    def __init__(self):
        self.template = None

    async def get_by_id(self, db, template_id):
        return self.template

    async def get_by_name(self, db, name):
        return self.template

    async def list_templates(self, db, page, page_size, search, media_type):
        return {
            "templates": [
                SimpleNamespace(
                    id="t1",
                    name="image_generate",
                    type=IMAGE_MINI_TOOLS_TYPE,
                    preview="preview/image.png",
                    prompt="prompt",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            "total": 1,
            "page": page,
            "page_size": page_size,
            "total_pages": 1,
        }


@pytest.mark.asyncio
async def test_list_media_templates_resolves_public_preview_urls(
    settings_factory, in_memory_storage
):
    repo = FakeMediaTemplateRepo()
    service = MediaTemplateService(
        repo=repo, media_storage=in_memory_storage, config=settings_factory()
    )

    result = await service.list_media_templates(db=None)

    assert result.total == 1
    assert result.templates[0].preview == "https://public.local/preview/image.png"


@pytest.mark.asyncio
async def test_get_media_tool_filters_non_mini_tools(settings_factory, in_memory_storage):
    repo = FakeMediaTemplateRepo()
    repo.template = SimpleNamespace(
        id="t2",
        name="anything",
        type="not-mini",
        preview="x.png",
        prompt="p",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    service = MediaTemplateService(
        repo=repo, media_storage=in_memory_storage, config=settings_factory()
    )

    tool = await service.get_media_tool(db=None, tool_id="t2")

    assert tool is None


def test_map_template_to_media_tool_applies_image_limits():
    tool = _map_template_to_media_tool({"id": "t1", "name": "image_generate", "preview": "p"})

    assert tool.id == "t1"
    assert tool.min_images <= tool.max_images
