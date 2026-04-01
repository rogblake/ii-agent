"""Coverage-focused tests for slide design dependency and router wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from ii_agent.content.slides.design.dependencies import (
    get_slide_design_repository,
    _get_slide_design_service as get_slide_design_service,
)
from ii_agent.content.slides.design.repository import SlideDesignRepository
from ii_agent.content.slides.design.router import (
    slide_deck_proxy_design_mode,
    slide_deck_sync_batch,
    slide_proxy_design_mode,
    slide_sync_batch,
)
from ii_agent.content.slides.design.schemas import (
    SlideDeckSyncBatchRequest,
    SlideSyncBatchRequest,
)
from ii_agent.content.slides.design.schemas import (
    SlideDeckSyncBatchResponse,
)


def test_get_slide_design_repository_returns_type():
    session_repo = object()
    slide_repo = object()
    repo = get_slide_design_repository(
        session_repo=session_repo,
        slide_repo=slide_repo,
    )
    assert isinstance(repo, SlideDesignRepository)


def test_get_slide_design_service_builds_service_with_dependencies(monkeypatch):
    captured = {}

    class FakeService:
        def __init__(self, *, repo, sandbox_service, config) -> None:
            captured["repo"] = repo
            captured["sandbox_service"] = sandbox_service
            captured["config"] = config

    class FakeSettings:
        mode = "unit"

    monkeypatch.setattr(
        "ii_agent.content.slides.design.dependencies.SlideDesignService", FakeService
    )
    monkeypatch.setattr(
        "ii_agent.content.slides.design.dependencies.get_settings", lambda: FakeSettings()
    )

    repo = get_slide_design_repository(object(), object())
    service = get_slide_design_service(
        design_repo=repo,
        sandbox_service=object(),
    )

    assert isinstance(service, FakeService)
    assert captured["repo"] is repo
    assert captured["config"].mode == "unit"


def _current_user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1")


async def _run_proxies():
    service = AsyncMock()
    service.get_slide_proxy_html.return_value = "<slide/>"
    service.get_slide_deck_proxy_html.return_value = "<deck/>"

    proxy = await slide_proxy_design_mode(
        _current_user(),
        None,
        service,
        session_id="session-1",
        presentation_name="deck",
        slide_number=2,
    )
    deck_proxy = await slide_deck_proxy_design_mode(
        _current_user(),
        None,
        service,
        session_id="session-1",
        presentation_name="deck",
    )

    return proxy, deck_proxy


def _stateful_responses():
    return (
        {
            "success": True,
            "processed": 1,
            "failed": 0,
            "errors": [],
        },
        {
            "success": True,
            "processed": 2,
            "failed": 1,
            "errors": ["retry"],
        },
    )


async def _run_sync_routes():
    slide_state_response, deck_state_response = _stateful_responses()

    sync_service = AsyncMock()
    sync_service.apply_slide_sync_batch.return_value = SlideDeckSyncBatchResponse(
        **slide_state_response
    )
    sync_service.apply_slide_deck_sync_batch.return_value = SlideDeckSyncBatchResponse(
        **deck_state_response
    )

    slide_request = SlideSyncBatchRequest(
        session_id="session-1",
        presentation_name="deck",
        slide_number=1,
        changes=[],
    )
    deck_request = SlideDeckSyncBatchRequest(
        session_id="session-1",
        presentation_name="deck",
        changes=[],
    )

    slide_result = await slide_sync_batch(
        slide_request,
        _current_user(),
        None,
        sync_service,
    )
    deck_result = await slide_deck_sync_batch(
        deck_request,
        _current_user(),
        None,
        sync_service,
    )

    return slide_result, deck_result


@pytest.mark.asyncio
async def test_slide_design_routers_delegate_to_service():
    proxy, deck_proxy = await _run_proxies()
    assert proxy.status_code == 200
    assert deck_proxy.status_code == 200

    slide_result, deck_result = await _run_sync_routes()
    assert slide_result.processed == 1
    assert deck_result.failed == 1
