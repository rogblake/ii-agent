from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agent.events.models import EventType
from ii_agent.agent.socket.command.file_content_handler import FileContentHandler

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_file_content_handler_emits_service_payload():
    event_stream = MagicMock()
    event_stream.publish = AsyncMock()

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

    handler = FileContentHandler(event_stream=event_stream, container=container)
    session_info = SimpleNamespace(id=uuid.uuid4())

    await handler.handle({"path": "/workspace/photo.avif"}, session_info)

    container.workspace_explorer_service.read_file.assert_awaited_once_with(
        session_info=session_info,
        path="/workspace/photo.avif",
    )
    published_event = event_stream.publish.await_args.args[0]
    assert published_event.type == EventType.FILE_CONTENT
    assert published_event.content == {
        "path": "/workspace/photo.avif",
        "content": None,
        "language": None,
        "file_kind": "image",
        "mime_type": "image/avif",
        "message": None,
        "too_big": False,
    }
