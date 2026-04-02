from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.sandbox_provider import SandboxProvider

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_sandbox_setter_binds_workspace_sync():
    workspace_explorer = MagicMock()
    workspace_explorer.build_workspace_event_publisher.return_value = AsyncMock()
    workspace_explorer.build_workspace_refresh_publisher.return_value = AsyncMock()
    container = MagicMock(workspace_explorer_service=workspace_explorer)
    provider = SandboxProvider(
        session_id="session-1",
        user_id="user-1",
        lock=asyncio.Lock(),
        container=container,
    )
    sandbox = MagicMock()
    sandbox.bind_workspace_sync = AsyncMock()

    provider.sandbox = sandbox
    await asyncio.sleep(0)

    sandbox.bind_workspace_sync.assert_awaited_once()
    workspace_explorer.build_workspace_event_publisher.assert_called_once_with(
        session_id="session-1",
        sandbox_manager=sandbox,
    )
    workspace_explorer.build_workspace_refresh_publisher.assert_called_once_with(
        session_id="session-1",
        sandbox_manager=sandbox,
    )
