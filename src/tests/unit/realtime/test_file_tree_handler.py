from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agent.events.models import EventType
from ii_agent.agent.socket.command.file_tree_handler import FileTreeHandler

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_file_tree_handler_calls_ensure_watching_and_emits_tree():
    event_stream = MagicMock()
    event_stream.publish = AsyncMock()

    container = MagicMock()
    container.workspace_explorer_service.ensure_watching = AsyncMock()
    container.workspace_explorer_service.get_tree = AsyncMock(
        return_value={
            "tree": {"path": "/workspace", "type": "directory", "children": []},
            "root_path": "/workspace",
            "contents": {},
        }
    )

    handler = FileTreeHandler(event_stream=event_stream, container=container)
    session_info = SimpleNamespace(id=uuid.uuid4())

    await handler.handle({}, session_info)

    container.workspace_explorer_service.ensure_watching.assert_awaited_once_with(
        session_info=session_info
    )
    container.workspace_explorer_service.get_tree.assert_awaited_once_with(
        session_info=session_info
    )
    published_event = event_stream.publish.await_args.args[0]
    assert published_event.type == EventType.FILE_TREE
    assert published_event.content["root_path"] == "/workspace"
