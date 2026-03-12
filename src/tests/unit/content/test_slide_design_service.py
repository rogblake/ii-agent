from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ii_agent.content.slides.design.schemas import SlideDeckSyncStateRequest
from ii_agent.content.slides.design.service import SlideDesignService


class _FakeRepo:
    def __init__(self):
        self.session = SimpleNamespace(id=str(uuid4()), user_id="user-1")
        self.session_for_user = self.session
        self.raw_changes = []
        self.raw_redo = []
        self.slides = []
        self.updated_slide_html: list[tuple[int, str]] = []
        self.updated_design_state = None

    async def get_session(self, db, session_id: str):
        return self.session

    def get_design_state(self, session):
        return self.raw_changes, self.raw_redo, 0

    async def get_presentation_slides(self, db, session_id: str, presentation_name: str):
        return self.slides

    async def get_session_for_user(self, db, session_id: str, user_id: str):
        return self.session_for_user

    async def get_slide(self, db, session_id: str, presentation_name: str, slide_number: int):
        for slide in self.slides:
            if int(getattr(slide, "slide_number", 0) or 0) == int(slide_number):
                return slide
        return None

    async def update_slide_html(self, db, slide, html: str, mark_synced: bool):
        slide.slide_content = html
        self.updated_slide_html.append((int(slide.slide_number), html))

    async def update_design_state(self, db, session, changes, redo_changes, updated_at):
        self.updated_design_state = {
            "changes": changes,
            "redo_changes": redo_changes,
            "updated_at": updated_at,
        }


class _FakeEventService:
    def __init__(self):
        self.saved = []
        self.emitted = []

    async def save_event(self, db, session_id, event):
        self.saved.append(event)
        return SimpleNamespace(id="evt-1")

    async def emit_event(self, event):
        self.emitted.append(event)


class _FakeSandbox:
    def __init__(self):
        self.commands: list[str] = []
        self.writes: dict[str, str] = {}

    async def run_command(self, cmd: str):
        self.commands.append(cmd)
        return ""

    async def write_file(self, path: str, content: str):
        self.writes[path] = content

    async def read_file(self, path: str):
        raise FileNotFoundError(path)


def _make_service(settings_factory, repo: _FakeRepo, sandbox_service, event_service=None):
    return SlideDesignService(
        repo=repo,
        sandbox_service=sandbox_service,
        config=settings_factory(),
    )


def _change_payload(
    *,
    design_id: str = "id-1",
    ts: int = 1000,
    slide_number: int = 1,
    change_type: str = "text",
    prop: str = "textContent",
    to_value: str = "new text",
):
    return {
        "designId": design_id,
        "type": change_type,
        "property": prop,
        "value": {"to": to_value},
        "timestamp": ts,
        "slideNumber": slide_number,
    }


def test_parse_persisted_design_changes_filters_and_sorts():
    parsed = SlideDesignService._parse_persisted_design_changes(
        [
            _change_payload(design_id="b", ts=2000),
            {"invalid": True},
            _change_payload(design_id="a", ts=1000),
        ]
    )

    assert [item.designId for item in parsed] == ["a", "b"]


def test_apply_single_change_unsupported_type():
    html, ok, reason = SlideDesignService._apply_single_change(
        "<div data-design-id='x'>x</div>",
        design_id="x",
        change_type="unknown",
        property_name="",
        new_value="",
    )

    assert ok is False
    assert html.startswith("<div")
    assert reason == "Unsupported change type: unknown"


@pytest.mark.asyncio
async def test_sync_persisted_slide_deck_changes_no_pending(settings_factory):
    repo = _FakeRepo()
    event_service = _FakeEventService()
    service = _make_service(
        settings_factory,
        repo=repo,
        sandbox_service=SimpleNamespace(get_sandbox_by_session_id=None),
        event_service=event_service,
    )

    response = await service.sync_persisted_slide_deck_changes(
        db=None,
        request=SlideDeckSyncStateRequest(
            session_id=repo.session.id,
            presentation_name="deck",
        ),
        user_id="user-1",
    )

    assert response.success is False
    assert response.applied == 0
    assert response.total == 0
    assert "No pending Slide Design Mode changes" in response.summary


@pytest.mark.asyncio
async def test_sync_persisted_slide_deck_changes_missing_slides(settings_factory):
    repo = _FakeRepo()
    repo.raw_changes = [_change_payload()]
    event_service = _FakeEventService()
    service = _make_service(
        settings_factory,
        repo=repo,
        sandbox_service=SimpleNamespace(get_sandbox_by_session_id=None),
        event_service=event_service,
    )

    response = await service.sync_persisted_slide_deck_changes(
        db=None,
        request=SlideDeckSyncStateRequest(
            session_id=repo.session.id,
            presentation_name="deck",
        ),
        user_id="user-1",
    )

    assert response.success is False
    assert response.applied == 0
    assert response.remaining == 1
    assert response.errors == ["No slides found for this presentation"]


@pytest.mark.asyncio
async def test_sync_persisted_slide_deck_changes_sandbox_unavailable(settings_factory, monkeypatch):
    repo = _FakeRepo()
    repo.raw_changes = [_change_payload()]
    repo.slides = [
        SimpleNamespace(slide_number=1, slide_content="<div>old</div>", slide_title="One"),
    ]
    event_service = _FakeEventService()
    sandbox_service = SimpleNamespace(get_sandbox_by_session_id=AsyncMock(return_value=None))
    service = _make_service(settings_factory, repo=repo, sandbox_service=sandbox_service, event_service=event_service)

    def _always_apply(html, **kwargs):
        return "<div>new</div>", True, None

    monkeypatch.setattr(
        SlideDesignService,
        "_apply_single_change",
        staticmethod(_always_apply),
    )

    response = await service.sync_persisted_slide_deck_changes(
        db=None,
        request=SlideDeckSyncStateRequest(
            session_id=repo.session.id,
            presentation_name="deck",
        ),
        user_id="user-1",
    )

    assert response.success is False
    assert response.applied == 0
    assert response.remaining == 1
    assert "sandbox was unavailable" in response.summary.lower()
    assert repo.updated_design_state is not None
    assert len(repo.updated_design_state["changes"]) == 1


@pytest.mark.asyncio
async def test_sync_persisted_slide_deck_changes_success(settings_factory, monkeypatch):
    repo = _FakeRepo()
    repo.raw_changes = [_change_payload(design_id="id-1", ts=1000)]
    repo.slides = [
        SimpleNamespace(
            slide_number=1,
            slide_content="<div data-design-id='id-1'>old</div>",
            slide_title="One",
        ),
    ]
    event_service = _FakeEventService()
    sandbox = _FakeSandbox()
    sandbox_service = SimpleNamespace(
        get_sandbox_by_session_id=AsyncMock(return_value=sandbox)
    )
    service = _make_service(settings_factory, repo=repo, sandbox_service=sandbox_service, event_service=event_service)

    def _always_apply(html, **kwargs):
        return "<div data-design-id='id-1'>new</div>", True, None

    monkeypatch.setattr(
        SlideDesignService,
        "_apply_single_change",
        staticmethod(_always_apply),
    )

    captured_summary = {}

    async def on_summary(summary: str) -> str | None:
        captured_summary["text"] = summary
        return "evt-callback"

    response = await service.sync_persisted_slide_deck_changes(
        db=None,
        request=SlideDeckSyncStateRequest(
            session_id=repo.session.id,
            presentation_name="deck",
        ),
        user_id="user-1",
        on_summary=on_summary,
    )

    assert response.success is True
    assert response.applied == 1
    assert response.remaining == 0
    assert response.event_id == "evt-callback"
    assert "text" in captured_summary
    assert repo.updated_slide_html
    assert repo.updated_design_state["changes"] == []
    assert any(path.endswith("/metadata.json") for path in sandbox.writes)


@pytest.mark.asyncio
async def test_get_slide_proxy_html_and_deck_proxy_html(settings_factory):
    repo = _FakeRepo()
    repo.slides = [
        SimpleNamespace(slide_number=1, slide_content="<html><body>One</body></html>", slide_title="One"),
        SimpleNamespace(slide_number=2, slide_content="<html><body>Two</body></html>", slide_title="Two"),
    ]
    service = _make_service(
        settings_factory,
        repo=repo,
        sandbox_service=SimpleNamespace(),
        event_service=_FakeEventService(),
    )

    single = await service.get_slide_proxy_html(
        db=None,
        session_id=repo.session.id,
        user_id="user-1",
        presentation_name="deck",
        slide_number=1,
    )
    assert "__DESIGN_MODE_RUNTIME__" in single

    deck = await service.get_slide_deck_proxy_html(
        db=None,
        session_id=repo.session.id,
        user_id="user-1",
        presentation_name="deck",
    )
    assert "__DESIGN_MODE_RUNTIME__" in deck
    assert "ii-slide-wrapper" in deck


@pytest.mark.asyncio
async def test_apply_slide_sync_batch_and_deck_sync_batch(settings_factory):
    from ii_agent.content.slides.design.schemas import (
        SlideDeckSyncBatchRequest,
        SlideDeckSyncChange,
        SlideSyncBatchRequest,
        SlideSyncChange,
    )

    repo = _FakeRepo()
    repo.slides = [
        SimpleNamespace(
            slide_number=1,
            slide_content='<p data-design-id="x">old</p>',
            slide_title="One",
        ),
        SimpleNamespace(
            slide_number=2,
            slide_content='<p data-design-id="y">old</p>',
            slide_title="Two",
        ),
    ]
    service = _make_service(
        settings_factory,
        repo=repo,
        sandbox_service=SimpleNamespace(),
        event_service=_FakeEventService(),
    )

    single = await service.apply_slide_sync_batch(
        db=None,
        user_id="user-1",
        request=SlideSyncBatchRequest(
            session_id=repo.session.id,
            presentation_name="deck",
            slide_number=1,
            changes=[
                SlideSyncChange(
                    design_id="x",
                    type="text",
                    property="textContent",
                    value={"to": "new"},
                )
            ],
        ),
    )
    assert single.success is True
    assert single.processed == 1

    deck = await service.apply_slide_deck_sync_batch(
        db=None,
        user_id="user-1",
        request=SlideDeckSyncBatchRequest(
            session_id=repo.session.id,
            presentation_name="deck",
            changes=[
                SlideDeckSyncChange(
                    slide_number=1,
                    design_id="x",
                    type="text",
                    property="textContent",
                    value={"to": "deck-new"},
                ),
                SlideDeckSyncChange(
                    slide_number=99,
                    design_id="z",
                    type="text",
                    property="textContent",
                    value={"to": "missing"},
                ),
            ],
        ),
    )
    assert deck.success is False
    assert deck.processed == 1
    assert deck.failed == 1
    assert any("Slide 99 not found" in msg for msg in deck.errors)
