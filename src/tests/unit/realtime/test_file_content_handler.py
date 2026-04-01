from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.realtime.events.app_events import FileContentEvent
from ii_agent.realtime.handlers.file_content_handler import FileContentHandler

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_file_content_handler_emits_service_payload():
    pubsub = AsyncMock()

    container = MagicMock()
    container.workspace_explorer_service.read_file = AsyncMock(
        return_value={
            "path": "/workspace/photo.avif",
            "content": None,
            "language": None,
            "file_kind": "image",
            "mime_type": "image/avif",
            "message": None,
            "too_big": False,
        }
    )

    handler = FileContentHandler(pubsub=pubsub, container=container)
    session_info = SimpleNamespace(id=uuid.uuid4())

    await handler.dispatch({"path": "/workspace/photo.avif"}, session_info)

    container.workspace_explorer_service.read_file.assert_awaited_once_with(
        session_info=session_info,
        path="/workspace/photo.avif",
    )
    pubsub.publish.assert_awaited_once()
    published_event = pubsub.publish.await_args.args[0]
    assert isinstance(published_event, FileContentEvent)
    assert published_event.content == {
        "path": "/workspace/photo.avif",
        "content": None,
        "language": None,
        "file_kind": "image",
        "mime_type": "image/avif",
        "message": None,
        "too_big": False,
    }
