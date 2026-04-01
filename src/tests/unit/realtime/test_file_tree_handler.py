from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.realtime.events.app_events import FileTreeEvent
from ii_agent.realtime.handlers.file_tree_handler import FileTreeHandler

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_file_tree_handler_calls_ensure_watching_and_emits_tree():
    pubsub = AsyncMock()

    container = MagicMock()
    container.workspace_explorer_service.ensure_watching = AsyncMock()
    container.workspace_explorer_service.get_tree = AsyncMock(
        return_value={
            "tree": {"path": "/workspace", "type": "directory", "children": []},
            "root_path": "/workspace",
            "contents": {},
        }
    )

    handler = FileTreeHandler(pubsub=pubsub, container=container)
    session_info = SimpleNamespace(id=uuid.uuid4())

    await handler.dispatch({}, session_info)

    container.workspace_explorer_service.ensure_watching.assert_awaited_once_with(
        session_info=session_info
    )
    container.workspace_explorer_service.get_tree.assert_awaited_once_with(
        session_info=session_info
    )
    pubsub.publish.assert_awaited_once()
    published_event = pubsub.publish.await_args.args[0]
    assert isinstance(published_event, FileTreeEvent)
    assert published_event.content["root_path"] == "/workspace"
