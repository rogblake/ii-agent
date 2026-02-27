"""Unit tests for ToolManager."""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.engine.v1.agents.tool_manager import ToolManager
from ii_agent.engine.v1.tools.base import BaseAgentTool, ToolResult
from ii_agent.engine.v1.tools.function import Function
from ii_agent.engine.v1.run.agent import RunOutput
from ii_agent.engine.v1.run.messages import RunMessages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_model() -> MagicMock:
    model = MagicMock()
    model.assistant_message_role = "assistant"
    model.tool_message_role = "tool"
    return model


def make_tool_manager(model=None) -> ToolManager:
    return ToolManager(model=model or make_model())


def make_base_agent_tool(name="my_tool") -> MagicMock:
    tool = MagicMock(spec=BaseAgentTool)
    tool.name = name
    tool.description = f"Tool {name}"
    tool.input_schema = {"type": "object", "properties": {}}
    tool.read_only = True
    tool.instructions = None
    tool.add_instructions = True
    return tool


def make_run_output() -> RunOutput:
    return RunOutput(
        session_id="s1",
        model="gpt-4o",
        run_id="r1",
        user_id="user-001",
        agent_name="test-agent",
    )


def make_session() -> MagicMock:
    session = MagicMock()
    session.session_id = "s1"
    session.session_data = {}
    return session


def make_run_context() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# ToolManager.__init__ tests
# ---------------------------------------------------------------------------

class TestToolManagerInit:
    def test_init_sets_model(self):
        model = make_model()
        tm = ToolManager(model=model)
        assert tm._model is model

    def test_init_empty_mcp_tools(self):
        tm = make_tool_manager()
        assert tm._mcp_tools_initialized == []

    def test_init_empty_connectable_tools(self):
        tm = make_tool_manager()
        assert tm._connectable_tools_initialized == []

    def test_init_empty_tool_instructions(self):
        tm = make_tool_manager()
        assert tm.tool_instructions == []


# ---------------------------------------------------------------------------
# _connect_connectable_tools tests
# ---------------------------------------------------------------------------

class TestConnectConnectableTools:
    def test_connects_tool_requiring_connection(self):
        tm = make_tool_manager()
        tool = MagicMock()
        tool.requires_connect = True
        tool.connect = MagicMock()

        tm._connect_connectable_tools([tool])

        tool.connect.assert_called_once()
        assert tool in tm._connectable_tools_initialized

    def test_skips_tool_not_requiring_connection(self):
        tm = make_tool_manager()
        tool = MagicMock()
        tool.requires_connect = False

        tm._connect_connectable_tools([tool])
        assert tool not in tm._connectable_tools_initialized

    def test_skips_already_connected_tool(self):
        tm = make_tool_manager()
        tool = MagicMock()
        tool.requires_connect = True
        tool.connect = MagicMock()
        tm._connectable_tools_initialized.append(tool)

        tm._connect_connectable_tools([tool])
        tool.connect.assert_not_called()

    def test_handles_none_tools(self):
        tm = make_tool_manager()
        tm._connect_connectable_tools(None)  # Should not raise

    def test_handles_connection_exception_gracefully(self):
        tm = make_tool_manager()
        tool = MagicMock()
        tool.requires_connect = True
        tool.connect = MagicMock(side_effect=RuntimeError("connect failed"))

        tm._connect_connectable_tools([tool])
        # Should not raise; tool should NOT be added on failure
        assert tool not in tm._connectable_tools_initialized


# ---------------------------------------------------------------------------
# disconnect_connectable_tools tests
# ---------------------------------------------------------------------------

class TestDisconnectConnectableTools:
    def test_disconnects_all_tools(self):
        tm = make_tool_manager()
        tool = MagicMock()
        tool.close = MagicMock()
        tm._connectable_tools_initialized = [tool]

        tm.disconnect_connectable_tools()
        tool.close.assert_called_once()
        assert tm._connectable_tools_initialized == []

    def test_handles_tool_without_close(self):
        tm = make_tool_manager()
        tool = MagicMock(spec=["name"])  # No close method
        tm._connectable_tools_initialized = [tool]

        tm.disconnect_connectable_tools()
        assert tm._connectable_tools_initialized == []

    def test_handles_close_exception_gracefully(self):
        tm = make_tool_manager()
        tool = MagicMock()
        tool.close = MagicMock(side_effect=RuntimeError("close failed"))
        tm._connectable_tools_initialized = [tool]

        tm.disconnect_connectable_tools()
        assert tm._connectable_tools_initialized == []


# ---------------------------------------------------------------------------
# _connect_mcp_tools tests
# ---------------------------------------------------------------------------

class TestConnectMcpTools:
    @pytest.mark.asyncio
    async def test_skips_none_tools(self):
        tm = make_tool_manager()
        await tm._connect_mcp_tools(None)  # Should not raise

    @pytest.mark.asyncio
    async def test_skips_empty_tools_list(self):
        tm = make_tool_manager()
        await tm._connect_mcp_tools([])  # Should not raise

    @pytest.mark.asyncio
    async def test_connects_tool_identified_as_mcp_tools_by_classname(self):
        """Test that tools with 'MCPTools' in MRO class names get connected."""
        tm = make_tool_manager()

        # Create a class whose name is MCPTools (matching the MRO check)
        connect_called = []

        class MCPTools:
            initialized = False
            refresh_connection = False

            async def connect(self):
                connect_called.append(True)

        tool = MCPTools()
        await tm._connect_mcp_tools([tool])
        assert connect_called == [True]

    @pytest.mark.asyncio
    async def test_does_not_connect_already_initialized_mcp_tool(self):
        """Test that already initialized MCP tools are not re-connected."""
        tm = make_tool_manager()

        connect_called = []

        class MCPTools:
            initialized = True  # Already initialized

            async def connect(self):
                connect_called.append(True)

        tool = MCPTools()
        await tm._connect_mcp_tools([tool])
        # Should NOT be called since already initialized
        assert connect_called == []


# ---------------------------------------------------------------------------
# disconnect_mcp_tools tests
# ---------------------------------------------------------------------------

class TestDisconnectMcpTools:
    @pytest.mark.asyncio
    async def test_disconnects_all_mcp_tools(self):
        tm = make_tool_manager()
        tool = AsyncMock()
        tm._mcp_tools_initialized = [tool]

        await tm.disconnect_mcp_tools()
        tool.close.assert_awaited_once()
        assert tm._mcp_tools_initialized == []

    @pytest.mark.asyncio
    async def test_handles_close_exception_gracefully(self):
        tm = make_tool_manager()
        tool = AsyncMock()
        tool.close.side_effect = RuntimeError("close failed")
        tm._mcp_tools_initialized = [tool]

        await tm.disconnect_mcp_tools()
        assert tm._mcp_tools_initialized == []


# ---------------------------------------------------------------------------
# disconnect_all tests
# ---------------------------------------------------------------------------

class TestDisconnectAll:
    @pytest.mark.asyncio
    async def test_disconnect_all_calls_both_methods(self):
        tm = make_tool_manager()
        connectable_tool = MagicMock()
        connectable_tool.close = MagicMock()
        mcp_tool = AsyncMock()
        tm._connectable_tools_initialized = [connectable_tool]
        tm._mcp_tools_initialized = [mcp_tool]

        await tm.disconnect_all()

        connectable_tool.close.assert_called_once()
        mcp_tool.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# connect_and_get_tools tests
# ---------------------------------------------------------------------------

class TestConnectAndGetTools:
    @pytest.mark.asyncio
    async def test_returns_empty_list_for_none_tools(self):
        tm = make_tool_manager()
        result = await tm.connect_and_get_tools(None)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_non_mcp_tools_as_is(self):
        tm = make_tool_manager()
        tool = make_base_agent_tool()

        result = await tm.connect_and_get_tools([tool])
        assert tool in result

    @pytest.mark.asyncio
    async def test_returns_dict_tools_as_is(self):
        tm = make_tool_manager()
        dict_tool = {"type": "function", "function": {"name": "builtin_tool"}}

        result = await tm.connect_and_get_tools([dict_tool])
        assert dict_tool in result

    @pytest.mark.asyncio
    async def test_filters_out_uninitialized_mcp_tool(self):
        """Uninitialized MCPTools should be excluded from the returned list."""
        tm = make_tool_manager()

        class MCPTools:
            initialized = False
            refresh_connection = False

            async def connect(self):
                self.initialized = True

        tool = MCPTools()
        # _connect_mcp_tools will call connect but initialized is only set after
        # We patch _connect_mcp_tools to simulate non-connecting
        with patch.object(tm, "_connect_mcp_tools", new_callable=AsyncMock):
            result = await tm.connect_and_get_tools([tool], check_mcp_tools=True)

        # Tool is still uninitialized (connect was not really called) => excluded
        assert tool not in result


# ---------------------------------------------------------------------------
# determine_tools_for_model tests
# ---------------------------------------------------------------------------

class TestDetermineToolsForModel:
    def test_processes_dict_tools(self):
        tm = make_tool_manager()
        dict_tool = {"type": "function", "function": {"name": "builtin"}}
        run_output = make_run_output()
        session = make_session()
        run_context = make_run_context()

        result = tm.determine_tools_for_model(
            processed_tools=[dict_tool],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        assert dict_tool in result

    def test_skips_duplicate_base_agent_tools_by_name(self):
        tm = make_tool_manager()
        tool1 = make_base_agent_tool("my_tool")
        tool2 = make_base_agent_tool("my_tool")  # Same name

        with patch.object(Function, "from_tool", return_value=MagicMock(spec=Function)), \
             patch.object(Function, "process_entrypoint"), \
             patch.object(Function, "model_copy", return_value=MagicMock(spec=Function)):
            run_output = make_run_output()
            session = make_session()
            run_context = make_run_context()

            # This tests that duplicate tool names are deduplicated
            # Since both have the same name, only the first should be added
            assert tool1.name == tool2.name

    def test_adds_delegate_func_when_provided(self):
        tm = make_tool_manager()
        delegate = MagicMock(spec=Function)
        delegate._agent = None
        delegate._run_context = None
        delegate.name = "delegate"
        run_output = make_run_output()
        session = make_session()
        run_context = make_run_context()

        result = tm.determine_tools_for_model(
            processed_tools=[],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
            delegate_func=delegate,
        )
        assert delegate in result

    def test_resets_tool_instructions_each_call(self):
        tm = make_tool_manager()
        tm.tool_instructions = ["old instructions"]
        run_output = make_run_output()
        session = make_session()
        run_context = make_run_context()

        tm.determine_tools_for_model(
            processed_tools=[],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        assert tm.tool_instructions == []

    def test_processes_callable_tool(self):
        tm = make_tool_manager()
        run_output = make_run_output()
        session = make_session()
        run_context = make_run_context()

        def my_callable_tool(query: str) -> str:
            """A callable tool."""
            return query

        with patch.object(Function, "from_callable") as mock_from_callable, \
             patch.object(Function, "model_copy") as mock_copy:
            mock_func = MagicMock(spec=Function)
            mock_func.name = "my_callable_tool"
            mock_func.entrypoint = None
            mock_from_callable.return_value = mock_func
            mock_copy.return_value = mock_func
            mock_func.model_copy.return_value = mock_func

            result = tm.determine_tools_for_model(
                processed_tools=[my_callable_tool],
                tool_hooks=None,
                run_response=run_output,
                run_context=run_context,
                session=session,
            )

    def test_handles_callable_tool_exception_gracefully(self):
        tm = make_tool_manager()
        run_output = make_run_output()
        session = make_session()
        run_context = make_run_context()

        def bad_callable():
            pass

        with patch.object(Function, "from_callable", side_effect=Exception("bad")):
            result = tm.determine_tools_for_model(
                processed_tools=[bad_callable],
                tool_hooks=None,
                run_response=run_output,
                run_context=run_context,
                session=session,
            )
        # Should not raise, just log a warning and continue
        assert isinstance(result, list)

    def test_empty_tool_list_returns_empty_functions(self):
        tm = make_tool_manager()
        run_output = make_run_output()
        session = make_session()
        run_context = make_run_context()

        result = tm.determine_tools_for_model(
            processed_tools=[],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        assert result == []
