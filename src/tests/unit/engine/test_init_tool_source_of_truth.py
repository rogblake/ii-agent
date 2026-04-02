from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.dev.init_tool import FullStackInitTool


def _make_tool() -> FullStackInitTool:
    tool = FullStackInitTool.__new__(FullStackInitTool)
    tool._persist_project_metadata = AsyncMock(return_value={"id": "proj-1", "name": "demo"})
    tool._save_database_url_to_secrets = AsyncMock()
    tool._get_active_database_payload = AsyncMock(
        return_value={
            "connection_string": "postgresql://project-db",
            "source": "neondb",
        }
    )
    return tool


@pytest.mark.asyncio
async def test_on_tool_end_uses_project_database_for_database_payload_and_secrets():
    tool = _make_tool()
    fc = MagicMock()
    fc.error = None
    fc.result = ToolResult(
        llm_content="ok",
        user_display_content={
            "project_name": "demo",
            "framework": "nextjs-shadcn",
            "directory": "/workspace/demo",
        },
        is_error=False,
    )
    agent = MagicMock()
    agent.session_id = "00000000-0000-4000-8000-000000000001"
    agent.user_id = "00000000-0000-4000-8000-000000000002"

    await tool.on_tool_end(agent, fc)

    tool._get_active_database_payload.assert_awaited_once_with(str(agent.session_id))
    tool._persist_project_metadata.assert_awaited_once_with(
        session_id=str(agent.session_id),
        project_name="demo",
        framework="nextjs-shadcn",
        project_path="/workspace/demo",
        description=None,
        database=None,
    )
    tool._save_database_url_to_secrets.assert_awaited_once_with(
        session_id=str(agent.session_id),
        user_id=str(agent.user_id),
        database_url="postgresql://project-db",
    )
    assert fc.result.user_display_content["database"] == {
        "connection_string": "postgresql://project-db",
        "source": "neondb",
    }
