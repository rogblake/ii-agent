from unittest.mock import AsyncMock

import pytest

import ii_agent.content.slides.templates.service as template_service_module
from ii_agent.content.slides.templates.schemas import SlideTemplateCreate
from ii_agent.content.slides.templates.service import SlideTemplateService


@pytest.mark.asyncio
async def test_slide_template_service_delegates_to_repository(settings_factory):
    repo = AsyncMock()
    repo.get_by_id.return_value = {
        "id": "tpl-1",
        "slide_content": {"title": "Hello"},
    }
    repo.get_full_by_id.return_value = {"id": "tpl-1"}
    repo.list_paginated.return_value = {"items": [], "total": 0}
    repo.create.return_value = {"id": "tpl-1"}

    service = SlideTemplateService(template_repo=repo, config=settings_factory())

    by_id = await service.get_slide_template_by_id(db=None, template_id="tpl-1")
    content = await service.get_slide_template_content_by_id(db=None, template_id="tpl-1")
    full = await service.get_slide_template_full_by_id(db=None, template_id="tpl-1")
    listed = await service.list_slide_templates(db=None, page=2, page_size=5, search="demo")

    created = await service.create_slide_template(
        db=None,
        template=SlideTemplateCreate(
            slide_template_name="Template",
            slide_content='{"title":"Slide"}',
            slide_template_images=["img-1"],
        ),
    )

    assert by_id["id"] == "tpl-1"
    assert content == {"title": "Hello"}
    assert full["id"] == "tpl-1"
    assert listed["total"] == 0
    assert created["id"] == "tpl-1"

    repo.create.assert_awaited_once_with(
        None,
        template_name="Template",
        content='{"title":"Slide"}',
        images=["img-1"],
    )


@pytest.mark.asyncio
async def test_module_level_wrappers_delegate_to_repository(monkeypatch):
    repo = AsyncMock()
    repo.get_by_id.return_value = {"id": "tpl-1", "slide_content": {"body": "x"}}
    repo.list_paginated.return_value = {"items": [{"id": "tpl-1"}], "total": 1}

    monkeypatch.setattr(template_service_module, "SlideTemplateRepository", lambda: repo)

    content = await template_service_module.get_slide_template_content_by_id(None, "tpl-1")
    listed = await template_service_module.list_slide_templates(
        None,
        page=3,
        page_size=10,
        search="starter",
    )

    assert content == {"body": "x"}
    assert listed["total"] == 1
    repo.get_by_id.assert_awaited_once_with(None, "tpl-1")
    repo.list_paginated.assert_awaited_once_with(None, 3, 10, "starter")
