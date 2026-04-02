from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.factory.tool_manager import AgentToolManager


@pytest.mark.asyncio
async def test_slide_write_tool_execute_writes_slide_and_metadata():
    tool = AgentToolManager.convert_tool("SlideWrite")
    assert tool is not None

    sandbox = MagicMock()
    sandbox.run_command = AsyncMock()
    sandbox.read_file = AsyncMock(side_effect=FileNotFoundError("missing"))
    sandbox.write_file = AsyncMock()
    tool.sandbox = sandbox

    html_content = "<!DOCTYPE html><html><head><title>Intro</title></head><body></body></html>"

    result = await tool.execute(
        {
            "presentation_name": "Team Deck",
            "slide_number": 1,
            "content": html_content,
            "title": "Intro",
            "description": "Opening slide",
            "type": "cover",
        }
    )

    assert result.is_error is False
    assert result.user_display_content == {
        "content": html_content,
        "filepath": "/workspace/presentations/Team_Deck/slide_001.html",
    }

    sandbox.run_command.assert_awaited_once_with("mkdir -p presentations/Team_Deck")
    sandbox.write_file.assert_any_await("presentations/Team_Deck/slide_001.html", html_content)

    metadata_call = next(
        call
        for call in sandbox.write_file.await_args_list
        if call.args[0] == "presentations/Team_Deck/metadata.json"
    )
    metadata = json.loads(metadata_call.args[1])

    assert metadata["presentation"]["name"] == "Team Deck"
    assert metadata["presentation"]["title"] == "Team Deck"
    assert metadata["slides"] == [
        {
            "id": "slide_001",
            "number": 1,
            "title": "Intro",
            "description": "Opening slide",
            "type": "cover",
            "filename": "slide_001.html",
            "file_path": "presentations/Team_Deck/slide_001.html",
            "preview_url": "/workspace/presentations/Team_Deck/slide_001.html",
            "created_at": metadata["slides"][0]["created_at"],
            "updated_at": metadata["slides"][0]["updated_at"],
        }
    ]
