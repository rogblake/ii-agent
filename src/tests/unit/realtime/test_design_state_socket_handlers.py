"""Unit tests for design state socket handlers."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.slides.design.schemas import SlideDeckSyncStateResponse
from ii_agent.projects.design.schemas import (
    DesignStateResponse,
    StyleChange,
)
from ii_agent.realtime.events.app_events import BaseEvent, SystemNotificationEvent
from ii_agent.realtime.handlers.design_get_state import DesignGetStateHandler
from ii_agent.realtime.handlers.design_save_state import DesignSaveStateHandler
from ii_agent.realtime.handlers.design_sync_state import DesignSyncStateHandler
from ii_agent.realtime.handlers.slide_deck_sync_state import SlideDeckSyncStateHandler
from ii_agent.realtime.schemas import (
    DesignGetStateContent,
    DesignSaveStateContent,
    DesignSyncStateContent,
    SlideDeckSyncStateContent,
)
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.projects.design.schemas import SyncStateResponse

pytestmark = pytest.mark.unit


class CapturingPubSub:
    """Minimal pubsub stub that captures published events."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish(self, event: BaseEvent) -> None:
        self.events.append(event)


def _make_container(**overrides: object) -> MagicMock:
    container = MagicMock()
    for key, value in overrides.items():
        setattr(container, key, value)
    return container


def _make_session_info() -> SessionInfo:
    return SessionInfo(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        api_version="v1",
        name="Design Session",
        status="active",
        workspace_dir="/workspace",
        is_public=False,
        created_at="2024-01-01T00:00:00Z",
        agent_type="website_build",
    )


def _make_state_response(session_id: str) -> DesignStateResponse:
    return DesignStateResponse(
        session_id=session_id,
        changes=[
            StyleChange(
                designId="hero-title",
                type="style",
                property="color",
                value={"value": "#111111"},
                timestamp=1,
            )
        ],
        redo_changes=[],
        updated_at=1234,
    )


def _make_remaining_change() -> StyleChange:
    return StyleChange(
        designId="hero-title",
        type="style",
        property="color",
        value={"value": "#111111"},
        timestamp=1,
    )


@asynccontextmanager
async def _db_cm():
    yield AsyncMock()


@pytest.mark.asyncio
async def test_design_get_state_handler_emits_loaded_response():
    session_info = _make_session_info()
    response = _make_state_response(str(session_info.id))
    pubsub = CapturingPubSub()
    project_design_service = MagicMock()
    project_design_service.get_design_state = AsyncMock(return_value=response)
    container = _make_container(project_design_service=project_design_service)
    handler = DesignGetStateHandler(pubsub=pubsub, container=container)

    with patch(
        "ii_agent.realtime.handlers.design_get_state.get_db_session_local",
        _db_cm,
    ):
        await handler.dispatch(
            {"command": "design_get_state", "session_id": str(session_info.id), "request_id": "req-1"},
            session_info,
        )

    assert len(pubsub.events) == 1
    event = pubsub.events[0]
    assert event.name == "system.notification"
    assert event.content["operation"] == "design_state_loaded"
    assert event.content["success"] is True
    assert event.content["request_id"] == "req-1"
    assert event.content["session_id"] == str(session_info.id)
    assert event.content["changes"][0]["designId"] == "hero-title"


@pytest.mark.asyncio
async def test_design_get_state_handler_emits_failure_on_service_error():
    session_info = _make_session_info()
    pubsub = CapturingPubSub()
    project_design_service = MagicMock()
    project_design_service.get_design_state = AsyncMock(side_effect=ValueError("Session not found"))
    container = _make_container(project_design_service=project_design_service)
    handler = DesignGetStateHandler(pubsub=pubsub, container=container)

    with patch(
        "ii_agent.realtime.handlers.design_get_state.get_db_session_local",
        _db_cm,
    ):
        await handler.dispatch(
            {"command": "design_get_state", "session_id": str(session_info.id), "request_id": "req-2"},
            session_info,
        )

    assert len(pubsub.events) == 1
    event = pubsub.events[0]
    assert event.name == "system.notification"
    assert event.content["operation"] == "design_state_loaded"
    assert event.content["success"] is False
    assert event.content["request_id"] == "req-2"


@pytest.mark.asyncio
async def test_design_save_state_handler_emits_saved_response():
    session_info = _make_session_info()
    response = _make_state_response(str(session_info.id))
    pubsub = CapturingPubSub()
    project_design_service = MagicMock()
    project_design_service.save_design_state = AsyncMock(return_value=response)
    container = _make_container(project_design_service=project_design_service)
    handler = DesignSaveStateHandler(pubsub=pubsub, container=container)

    with patch(
        "ii_agent.realtime.handlers.design_save_state.get_db_session_local",
        _db_cm,
    ):
        await handler.dispatch(
            {
                "command": "design_save_state",
                "session_id": str(session_info.id),
                "request_id": "req-3",
                "changes": [
                    {
                        "designId": "hero-title",
                        "type": "style",
                        "property": "color",
                        "value": {"value": "#111111"},
                        "timestamp": 1,
                    }
                ],
            },
            session_info,
        )

    assert len(pubsub.events) == 1
    event = pubsub.events[0]
    assert event.name == "system.notification"
    assert event.content["operation"] == "design_state_saved"
    assert event.content["success"] is True
    assert event.content["request_id"] == "req-3"
    assert event.content["session_id"] == str(session_info.id)
    assert event.content["updated_at"] == 1234


@pytest.mark.asyncio
async def test_design_sync_state_handler_emits_remaining_changes():
    session_info = _make_session_info()
    response = SyncStateResponse(
        success=False,
        applied=1,
        total=2,
        remaining=1,
        errors=["Failed to sync hero title"],
        summary="Applied 1 of 2 design changes.",
        remaining_changes=[_make_remaining_change()],
        event_id="evt-design-sync",
    )
    pubsub = CapturingPubSub()
    project_design_service = MagicMock()
    project_design_service.sync_persisted_design_changes = AsyncMock(return_value=response)
    container = _make_container(
        project_design_service=project_design_service,
        event_service=MagicMock(),
    )
    handler = DesignSyncStateHandler(pubsub=pubsub, container=container)

    with patch(
        "ii_agent.realtime.handlers.design_sync_state.get_db_session_local",
        _db_cm,
    ):
        await handler.dispatch(
            {"command": "design_sync_state", "session_id": str(session_info.id)},
            session_info,
        )

    assert len(pubsub.events) == 1
    event = pubsub.events[0]
    assert event.name == "system.notification"
    assert event.content["operation"] == "design_sync_state_complete"
    assert event.content["remaining"] == 1
    assert event.content["remaining_changes"][0]["designId"] == "hero-title"
    assert event.content["event_id"] == "evt-design-sync"


@pytest.mark.asyncio
async def test_slide_deck_sync_state_handler_emits_remaining_changes():
    session_info = _make_session_info()
    response = SlideDeckSyncStateResponse(
        success=False,
        applied=1,
        total=2,
        remaining=1,
        errors=["Failed to sync hero title"],
        summary="Applied 1 of 2 slide design changes.",
        remaining_changes=[_make_remaining_change()],
        event_id="evt-slide-sync",
    )
    pubsub = CapturingPubSub()
    slide_design_service = MagicMock()
    slide_design_service.sync_persisted_slide_deck_changes = AsyncMock(return_value=response)
    container = _make_container(
        slide_design_service=slide_design_service,
        event_service=MagicMock(),
    )
    handler = SlideDeckSyncStateHandler(pubsub=pubsub, container=container)

    with patch(
        "ii_agent.realtime.handlers.slide_deck_sync_state.get_db_session_local",
        _db_cm,
    ):
        await handler.dispatch(
            {
                "command": "slide_deck_sync_state",
                "session_id": str(session_info.id),
                "presentation_name": "Deck",
            },
            session_info,
        )

    assert len(pubsub.events) == 1
    event = pubsub.events[0]
    assert event.name == "system.notification"
    assert event.content["operation"] == "slide_deck_sync_state_complete"
    assert event.content["remaining"] == 1
    assert event.content["remaining_changes"][0]["designId"] == "hero-title"
    assert event.content["event_id"] == "evt-slide-sync"
