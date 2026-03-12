"""Unit tests for design state socket handlers."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.events.models import EventType, RealtimeEvent
from ii_agent.content.slides.design.schemas import SlideDeckSyncStateResponse
from ii_agent.projects.design.schemas import (
    DesignStateResponse,
    SyncStateResponse,
    StyleChange,
)
from ii_agent.sessions.schemas import SessionInfo

pytestmark = pytest.mark.unit


class CapturingEventStream:
    def __init__(self) -> None:
        self.events: list[RealtimeEvent] = []

    async def publish(self, event: RealtimeEvent) -> None:
        self.events.append(event)


def _make_session_info() -> SessionInfo:
    return SessionInfo(
        id=uuid.uuid4(),
        user_id="user-123",
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
    from ii_agent.agent.socket.command.design_get_state_handler import (
        DesignGetStateHandler,
    )

    session_info = _make_session_info()
    response = _make_state_response(str(session_info.id))
    stream = CapturingEventStream()
    container = MagicMock()
    container.project_design_service.get_design_state = AsyncMock(
        return_value=response
    )
    handler = DesignGetStateHandler(event_stream=stream, container=container)

    with patch(
        "ii_agent.agent.socket.command.design_get_state_handler.get_db_session_local",
        _db_cm,
    ):
        await handler.handle(
            {"session_id": str(session_info.id), "request_id": "req-1"},
            session_info,
        )

    assert len(stream.events) == 1
    event = stream.events[0]
    assert event.type == EventType.SYSTEM
    assert event.content["operation"] == "design_state_loaded"
    assert event.content["success"] is True
    assert event.content["request_id"] == "req-1"
    assert event.content["session_id"] == str(session_info.id)
    assert event.content["changes"][0]["designId"] == "hero-title"


@pytest.mark.asyncio
async def test_design_get_state_handler_emits_failure_response_for_invalid_payload():
    from ii_agent.agent.socket.command.design_get_state_handler import (
        DesignGetStateHandler,
    )

    session_info = _make_session_info()
    stream = CapturingEventStream()
    container = MagicMock()
    handler = DesignGetStateHandler(event_stream=stream, container=container)

    await handler.handle({"request_id": "req-2"}, session_info)

    assert len(stream.events) == 1
    event = stream.events[0]
    assert event.type == EventType.SYSTEM
    assert event.content["operation"] == "design_state_loaded"
    assert event.content["success"] is False
    assert event.content["request_id"] == "req-2"
    assert "Invalid design state request" in event.content["error"]


@pytest.mark.asyncio
async def test_design_save_state_handler_emits_saved_response():
    from ii_agent.agent.socket.command.design_save_state_handler import (
        DesignSaveStateHandler,
    )

    session_info = _make_session_info()
    response = _make_state_response(str(session_info.id))
    stream = CapturingEventStream()
    container = MagicMock()
    container.project_design_service.save_design_state = AsyncMock(
        return_value=response
    )
    handler = DesignSaveStateHandler(event_stream=stream, container=container)

    with patch(
        "ii_agent.agent.socket.command.design_save_state_handler.get_db_session_local",
        _db_cm,
    ):
        await handler.handle(
            {
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

    assert len(stream.events) == 1
    event = stream.events[0]
    assert event.type == EventType.SYSTEM
    assert event.content["operation"] == "design_state_saved"
    assert event.content["success"] is True
    assert event.content["request_id"] == "req-3"
    assert event.content["session_id"] == str(session_info.id)
    assert event.content["updated_at"] == 1234


@pytest.mark.asyncio
async def test_design_sync_state_handler_emits_remaining_changes():
    from ii_agent.agent.socket.command.design_sync_state_handler import (
        DesignSyncStateHandler,
    )

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
    stream = CapturingEventStream()
    container = MagicMock()
    container.project_design_service.sync_persisted_design_changes = AsyncMock(
        return_value=response
    )
    handler = DesignSyncStateHandler(event_stream=stream, container=container)

    with patch(
        "ii_agent.agent.socket.command.design_sync_state_handler.get_db_session_local",
        _db_cm,
    ):
        await handler.handle({"session_id": str(session_info.id)}, session_info)

    assert len(stream.events) == 1
    event = stream.events[0]
    assert event.type == EventType.SYSTEM
    assert event.content["operation"] == "design_sync_state_complete"
    assert event.content["remaining"] == 1
    assert event.content["remaining_changes"][0]["designId"] == "hero-title"
    assert event.content["event_id"] == "evt-design-sync"


@pytest.mark.asyncio
async def test_slide_deck_sync_state_handler_emits_remaining_changes():
    from ii_agent.agent.socket.command.slide_deck_sync_state_handler import (
        SlideDeckSyncStateHandler,
    )

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
    stream = CapturingEventStream()
    container = MagicMock()
    container.slide_design_service.sync_persisted_slide_deck_changes = AsyncMock(
        return_value=response
    )
    handler = SlideDeckSyncStateHandler(event_stream=stream, container=container)

    with patch(
        "ii_agent.agent.socket.command.slide_deck_sync_state_handler.get_db_session_local",
        _db_cm,
    ):
        await handler.handle(
            {
                "session_id": str(session_info.id),
                "presentation_name": "Deck",
            },
            session_info,
        )

    assert len(stream.events) == 1
    event = stream.events[0]
    assert event.type == EventType.SYSTEM
    assert event.content["operation"] == "slide_deck_sync_state_complete"
    assert event.content["remaining"] == 1
    assert event.content["remaining_changes"][0]["designId"] == "hero-title"
    assert event.content["event_id"] == "evt-slide-sync"
