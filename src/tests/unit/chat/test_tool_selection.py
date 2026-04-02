from types import SimpleNamespace

import pytest

from ii_agent.chat.schemas import ErrorTextContent, ToolResult
from ii_agent.chat.tool_service import ChatToolService


@pytest.mark.asyncio
async def test_execute_tool_returns_unknown_tool_error():
    result = await ChatToolService.execute_tool(
        tool_call_id="call-1",
        tool_name="missing-tool",
        tool_input="{}",
        tool_registry={},
    )

    assert isinstance(result, ToolResult)
    assert isinstance(result.output, ErrorTextContent)
    assert "Unknown tool" in result.output.value


@pytest.mark.asyncio
async def test_execute_tool_returns_tool_response():
    class FakeTool:
        async def run(self, call_input):
            return SimpleNamespace(output=SimpleNamespace(model_dump=lambda: {"ok": True}, type="json", value={"ok": True}))

    registry = {"demo": FakeTool()}

    result = await ChatToolService.execute_tool(
        tool_call_id="call-1",
        tool_name="demo",
        tool_input="{}",
        tool_registry=registry,
    )

    assert result.name == "demo"


@pytest.mark.asyncio
async def test_build_tool_registry_returns_empty_when_no_tools(settings_factory):
    service = ChatToolService(
        user_service=SimpleNamespace(get_active_api_key=lambda *args, **kwargs: "key"),
        connector_repo=SimpleNamespace(get_by_user=lambda *args, **kwargs: []),
        container=SimpleNamespace(),
        config=settings_factory(),
    )

    registry, tools = await service.build_tool_registry(
        db=None,
        user_id="u1",
        session_id="s1",
        tools={},
        chat_request=SimpleNamespace(github_repository=None),
        vector_store=None,
        media_context=None,
    )

    assert registry == {}
    assert tools == []
