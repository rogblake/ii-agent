from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.content.storybook.edit_service import StorybookEditService
from ii_agent.content.storybook.schemas import DesignChange


class _FakeRepo:
    def __init__(self):
        self.storybook = None
        self.family = []

    async def get_page_by_number(self, db, storybook_id: str, page_number: int):
        return None

    async def get_by_id(self, db, storybook_id: str):
        return self.storybook

    async def get_version_family(self, db, root_id: str):
        return self.family


class _FakeVersionService:
    def __init__(self):
        self.create_storybook_version_multi_page = AsyncMock(return_value=None)


def _change(**overrides) -> DesignChange:
    payload = {
        "designId": "id-1",
        "type": "attribute",
        "property": "title",
        "value": {"from": "Old", "to": "New"},
        "timestamp": 1000,
        "elementContext": {"tagName": "div"},
    }
    payload.update(overrides)
    return DesignChange.model_validate(payload)


@pytest.mark.asyncio
async def test_save_all_page_edits_returns_none_for_missing_storybook():
    repo = _FakeRepo()
    version_service = _FakeVersionService()
    service = StorybookEditService(repo=repo, version_service=version_service)

    storybook, voice_cost = await service.save_all_page_edits(
        db=None,
        storybook_id="missing",
        page_changes={1: [_change()]},
        image_urls={},
    )

    assert storybook is None
    assert voice_cost == 0.0


@pytest.mark.asyncio
async def test_save_all_page_edits_no_effective_updates_returns_none(monkeypatch):
    repo = _FakeRepo()
    repo.storybook = SimpleNamespace(
        id="sb-1",
        session_id="session-1",
        style_json={},
        pages=[SimpleNamespace(page_number=2, html_content="<p>x</p>")],
    )
    version_service = _FakeVersionService()
    service = StorybookEditService(repo=repo, version_service=version_service)
    monkeypatch.setattr(
        service,
        "apply_changes_to_html",
        AsyncMock(return_value="<p>x</p>"),
    )

    storybook, voice_cost = await service.save_all_page_edits(
        db=None,
        storybook_id="sb-1",
        page_changes={1: [_change()]},  # page 1 missing in source pages
        image_urls={},
    )

    assert storybook is None
    assert voice_cost == 0.0
    version_service.create_storybook_version_multi_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_all_page_edits_version_conflict_path():
    repo = _FakeRepo()
    repo.storybook = SimpleNamespace(
        id="sb-1",
        session_id="session-1",
        style_json={},
        pages=[SimpleNamespace(page_number=1, html_content="<p>old</p>")],
    )
    version_service = _FakeVersionService()
    version_service.create_storybook_version_multi_page = AsyncMock(return_value=None)
    service = StorybookEditService(repo=repo, version_service=version_service)

    storybook, voice_cost = await service.save_all_page_edits(
        db=None,
        storybook_id="sb-1",
        page_changes={
            1: [
                _change(
                    type="text",
                    property="textContent",
                    value={"from": "old", "to": "new"},
                )
            ]
        },
        image_urls={},
    )

    assert storybook is None
    assert voice_cost == 0.0
    version_service.create_storybook_version_multi_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_version_history_handles_cycle_without_root():
    repo = _FakeRepo()
    repo.storybook = SimpleNamespace(
        id="a",
        parent_storybook_id="b",
        root_storybook_id=None,
    )

    async def _get_by_id(db, storybook_id: str):
        if storybook_id == "a":
            return SimpleNamespace(id="a", parent_storybook_id="b", root_storybook_id=None)
        if storybook_id == "b":
            return SimpleNamespace(id="b", parent_storybook_id="a", root_storybook_id=None)
        return None

    repo.get_by_id = _get_by_id
    repo.get_version_family = AsyncMock(return_value=[])
    version_service = _FakeVersionService()
    service = StorybookEditService(repo=repo, version_service=version_service)

    versions = await service.get_version_history(db=None, storybook_id="a")
    assert versions == []


def test_apply_attribute_change_missing_target_returns_false():
    service = StorybookEditService(repo=_FakeRepo(), version_service=_FakeVersionService())
    updated, ok = service._apply_attribute_change(
        "<div>no target</div>",
        design_id="missing",
        attr="title",
        value="new",
        context=None,
    )

    assert ok is False
    assert updated == "<div>no target</div>"


def test_apply_attribute_change_context_fallback_sets_design_id():
    service = StorybookEditService(repo=_FakeRepo(), version_service=_FakeVersionService())
    updated, ok = service._apply_attribute_change(
        "<button class='primary'>Save</button>",
        design_id="btn-1",
        attr="className",
        value="primary active",
        context={"tagName": "button", "className": "primary"},
    )

    assert ok is True
    assert 'data-design-id="btn-1"' in updated
    assert "active" in updated
