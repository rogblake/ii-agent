"""Deep unit tests for engine/runtime - focusing on uncovered branches.

This module covers:
1. ResponseHandler._handle_model_response_chunk: streaming event branches
2. ResponseHandler.handle_model_response_stream: sandbox initialization, stream events
3. ToolManager.run_tool: tool execution events
4. ToolManager.connect_and_get_tools: MCP tool refresh connection
5. ToolManager.determine_tools_for_model: Toolkit, Function, callable processing
6. utils/agent.py: await_for_thread_tasks_stream, wait_for_thread_tasks_stream
7. factory/converter.py: RunPausedEvent with tools/requirements, ToolCallStarted/Completed
8. factory/converter.py: SandboxInitializedEvent
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ii_agent.agent.runtime.agents.response_handler import ResponseHandler
from ii_agent.agent.runtime.agents.tool_manager import ToolManager
from ii_agent.agent.runtime.models.response import ModelResponse, ModelResponseEvent, ToolExecution
from ii_agent.agent.runtime.run.agent import RunOutput, RunEvent, RunInput
from ii_agent.agent.runtime.run.messages import RunMessages
from ii_agent.agent.runtime.models.message import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_model(assistant_role="assistant", tool_role="tool") -> MagicMock:
    model = MagicMock()
    model.assistant_message_role = assistant_role
    model.tool_message_role = tool_role
    return model


def make_run_output(**kwargs) -> RunOutput:
    defaults = dict(
        run_id=str(uuid4()),
        session_id="session-deep",
        user_id="user-deep",
        model="gpt-4o",
        agent_name="DeepAgent",
    )
    defaults.update(kwargs)
    return RunOutput(**defaults)


def make_run_messages(messages=None) -> RunMessages:
    rm = RunMessages()
    if messages:
        rm.messages = messages
    return rm


def make_session(session_id="session-deep") -> MagicMock:
    session = MagicMock()
    session.session_id = session_id
    session.session_data = None
    session.runs = []
    return session


# ---------------------------------------------------------------------------
# ResponseHandler._handle_model_response_chunk tests
# ---------------------------------------------------------------------------

class TestHandleModelResponseChunkDeep:
    """Test the internal _handle_model_response_chunk method."""

    def _make_handler(self) -> ResponseHandler:
        return ResponseHandler(model=make_model())

    def _make_model_response(self) -> ModelResponse:
        return ModelResponse(content="")

    def test_run_output_event_custom_event_sets_session_id(self):
        from ii_agent.agent.runtime.run.agent import CustomEvent
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        custom_event = CustomEvent(
            event="CustomEvent",
            agent_id="a1",
            agent_name="A",
            run_id=run_output.run_id,
        )

        events = list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=custom_event,
            stream_events=False,
        ))
        assert len(events) == 1
        # Custom event should have session_id set
        assert custom_event.session_id == session.session_id

    def test_assistant_response_delta_content_accumulated(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        chunk = ModelResponse(
            content="Hello",
            event=ModelResponseEvent.assistant_response.value,
        )
        chunk.is_delta = True

        events = list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert model_response.content == "Hello"

    def test_assistant_response_non_delta_content_set(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        chunk = ModelResponse(
            content="Full response",
            event=ModelResponseEvent.assistant_response.value,
        )
        chunk.is_delta = False

        events = list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert model_response.content == "Full response"
        assert run_output.content == "Full response"

    def test_reasoning_started_delta_with_stream_events(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            reasoning_content="Starting to think",
        )
        chunk.is_delta = True
        chunk.delta_status = "reasoning_started"

        events = list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=True,  # Stream events enabled
        ))
        # Should yield at least one reasoning_started event
        assert len(events) >= 1

    def test_reasoning_done_delta_with_stream_events(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        model_response.reasoning_content = "Final reasoning"
        session = make_session()

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            reasoning_content="Final reasoning",
        )
        chunk.is_delta = True
        chunk.delta_status = "reasoning_done"

        events = list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=True,
        ))
        assert len(events) >= 1

    def test_reasoning_delta_accumulates_content(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        model_response.reasoning_content = "Part 1 "
        session = make_session()

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            reasoning_content=" Part 2",
        )
        chunk.is_delta = True
        chunk.delta_status = "thinking"

        handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        )
        # Forces iteration
        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert "Part 2" in (model_response.reasoning_content or "")

    def test_redacted_reasoning_content_accumulated(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
        )
        chunk.is_delta = True
        chunk.delta_status = None
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = "<encrypted_block>"

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert model_response.reasoning_content == "<encrypted_block>"

    def test_redacted_reasoning_appended_to_existing(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        model_response.reasoning_content = "existing "
        session = make_session()

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
        )
        chunk.is_delta = True
        chunk.delta_status = None
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = "redacted_part"

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert "existing " in model_response.reasoning_content
        assert "redacted_part" in model_response.reasoning_content

    def test_provider_data_set_on_run_response(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            provider_data={"usage": {"tokens": 100}},
        )
        chunk.is_delta = False
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert run_output.model_provider_data == {"usage": {"tokens": 100}}

    def test_citations_set_on_run_response(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        citations = [{"url": "http://example.com"}]
        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            citations=citations,
        )
        chunk.is_delta = False
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert run_output.citations == citations

    def test_tool_call_paused_event_adds_requirements(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        tool_exec = MagicMock()
        chunk = ModelResponse(
            event=ModelResponseEvent.tool_call_paused.value,
            tool_executions=[tool_exec],
        )

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert run_output.tools is not None
        assert run_output.requirements is not None

    def test_tool_call_started_event_with_stream_events(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        tool_exec = MagicMock(spec=ToolExecution)
        tool_exec.tool_name = "my_tool"
        chunk = ModelResponse(
            event=ModelResponseEvent.tool_call_started.value,
            tool_executions=[tool_exec],
        )

        events = list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=True,
        ))
        # Should yield a tool_call_started event
        assert len(events) >= 1

    def test_tool_call_completed_updates_tool_result(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        existing_tool = MagicMock(spec=ToolExecution)
        existing_tool.tool_call_id = "tc-001"
        run_output.tools = [existing_tool]

        completed_tool = MagicMock(spec=ToolExecution)
        completed_tool.tool_call_id = "tc-001"
        completed_tool.result = "result!"
        completed_tool.tool_call_error = False

        chunk = ModelResponse(
            event=ModelResponseEvent.tool_call_completed.value,
            tool_executions=[completed_tool],
        )
        chunk.updated_session_state = None
        chunk.images = None
        chunk.videos = None
        chunk.audios = None
        chunk.files = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        # The tool at index 0 should be updated
        assert run_output.tools[0] is completed_tool

    def test_tool_call_completed_updates_session_state(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()
        session.session_data = {"session_state": {"existing_key": "value"}}
        session_state = {"local_key": "local_value"}

        completed_tool = MagicMock(spec=ToolExecution)
        completed_tool.tool_call_id = "tc-002"
        completed_tool.result = "done"
        completed_tool.tool_call_error = False

        chunk = ModelResponse(
            event=ModelResponseEvent.tool_call_completed.value,
            tool_executions=[completed_tool],
        )
        chunk.updated_session_state = {"new_key": "new_value"}
        chunk.images = None
        chunk.videos = None
        chunk.audios = None
        chunk.files = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
            session_state=session_state,
        ))
        assert "new_key" in session_state

    def test_tool_call_completed_adds_images_to_run_response(self):
        from ii_agent.agent.runtime.media import Image
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        img = Image(id="img-1", url="http://example.com/img.png")
        completed_tool = MagicMock(spec=ToolExecution)
        completed_tool.tool_call_id = "tc-003"
        completed_tool.result = "done"
        completed_tool.tool_call_error = False

        chunk = ModelResponse(
            event=ModelResponseEvent.tool_call_completed.value,
            tool_executions=[completed_tool],
        )
        chunk.updated_session_state = None
        chunk.images = [img]
        chunk.videos = None
        chunk.audios = None
        chunk.files = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert run_output.images is not None
        assert img in run_output.images

    def test_audio_content_base64_decoded(self):
        import base64
        from ii_agent.agent.runtime.media import Audio as AudioMedia

        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        audio_bytes = b"fake_audio_data"
        encoded = base64.b64encode(audio_bytes).decode("utf-8")

        audio_mock = MagicMock()
        audio_mock.id = "audio-1"
        audio_mock.content = encoded  # base64 string
        audio_mock.transcript = "hello"
        audio_mock.expires_at = None
        audio_mock.mime_type = None
        audio_mock.sample_rate = None
        audio_mock.channels = None

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            audio=audio_mock,
        )
        chunk.is_delta = False
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        # Audio should have been processed
        assert model_response.audio is not None

    def test_audio_content_bytes_appended(self):
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        audio_mock = MagicMock()
        audio_mock.id = "audio-2"
        audio_mock.content = b"raw_bytes"
        audio_mock.transcript = "world"
        audio_mock.expires_at = None
        audio_mock.mime_type = None
        audio_mock.sample_rate = None
        audio_mock.channels = None

        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            audio=audio_mock,
        )
        chunk.is_delta = False
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert model_response.audio is not None
        assert b"raw_bytes" in model_response.audio.content

    def test_images_response_added_to_model_response(self):
        from ii_agent.agent.runtime.media import Image
        handler = self._make_handler()
        run_output = make_run_output()
        model_response = self._make_model_response()
        session = make_session()

        img = Image(id="img-resp", url="http://example.com/resp.png")
        chunk = ModelResponse(
            event=ModelResponseEvent.assistant_response.value,
            images=[img],
        )
        chunk.is_delta = False
        chunk.reasoning_content = None
        chunk.redacted_reasoning_content = None
        chunk.content = None

        list(handler._handle_model_response_chunk(
            session=session,
            run_response=run_output,
            model_response=model_response,
            model_response_event=chunk,
            stream_events=False,
        ))
        assert model_response.images is not None
        assert img in model_response.images


# ---------------------------------------------------------------------------
# ToolManager.run_tool tests
# ---------------------------------------------------------------------------

class TestToolManagerRunToolDeep:
    def _make_tool_manager(self) -> ToolManager:
        return ToolManager(model=make_model())

    @pytest.mark.asyncio
    async def test_run_tool_appends_function_call_results(self):
        tm = self._make_tool_manager()
        run_output = make_run_output()
        run_messages = make_run_messages()

        tool_exec = MagicMock(spec=ToolExecution)
        tool_exec.tool_name = "test_tool"
        tool_exec.tool_call_id = "tc-001"

        function_call = MagicMock()

        # Mock model methods
        tm._model.get_function_call_to_run_from_tool_execution = MagicMock(return_value=function_call)

        result_msg = Message(role="tool", content="tool result")
        result_msg.tool_call_id = "tc-001"

        async def mock_arun(*args, **kwargs):
            kwargs["function_call_results"].append(result_msg)
            completed = ModelResponse(
                event=ModelResponseEvent.tool_call_completed.value,
                tool_executions=[tool_exec],
            )
            yield completed

        tm._model.arun_function_calls = mock_arun

        async def collect():
            results = []
            async for event in tm.run_tool(
                run_response=run_output,
                run_messages=run_messages,
                tool=tool_exec,
                functions=None,
                stream_events=False,
            ):
                results.append(event)
            return results

        await collect()
        assert len(run_messages.messages) > 0

    @pytest.mark.asyncio
    async def test_run_tool_yields_started_event_when_stream(self):
        tm = self._make_tool_manager()
        run_output = make_run_output()
        run_messages = make_run_messages()

        tool_exec = MagicMock(spec=ToolExecution)
        tool_exec.tool_name = "test_tool"
        tool_exec.tool_call_id = "tc-002"

        tm._model.get_function_call_to_run_from_tool_execution = MagicMock(return_value=MagicMock())

        async def mock_arun(*args, **kwargs):
            started = ModelResponse(
                event=ModelResponseEvent.tool_call_started.value,
            )
            yield started

        tm._model.arun_function_calls = mock_arun

        events = []
        async for event in tm.run_tool(
            run_response=run_output,
            run_messages=run_messages,
            tool=tool_exec,
            functions=None,
            stream_events=True,
        ):
            events.append(event)

        assert len(events) >= 1


# ---------------------------------------------------------------------------
# ToolManager.connect_and_get_tools deep tests
# ---------------------------------------------------------------------------

class TestConnectAndGetToolsDeep:
    @pytest.mark.asyncio
    async def test_mcp_tool_with_refresh_connection_reconnects_when_not_alive(self):
        tm = ToolManager(model=make_model())

        class MCPTools:
            initialized = True
            refresh_connection = True

            async def is_alive(self):
                return False

            async def connect(self, force=False):
                self.initialized = True

            async def build_tools(self):
                pass

        tool = MCPTools()
        result = await tm.connect_and_get_tools([tool])
        assert tool in result

    @pytest.mark.asyncio
    async def test_mcp_tool_with_refresh_connection_alive_skips_reconnect(self):
        tm = ToolManager(model=make_model())

        build_called = []

        class MCPTools:
            initialized = True
            refresh_connection = True

            async def is_alive(self):
                return True

            async def connect(self, force=False):
                pass

            async def build_tools(self):
                build_called.append(True)

        tool = MCPTools()
        result = await tm.connect_and_get_tools([tool])
        assert build_called == [True]

    @pytest.mark.asyncio
    async def test_mcp_tool_with_is_alive_exception_skips_tool(self):
        tm = ToolManager(model=make_model())

        class MCPTools:
            initialized = True
            refresh_connection = True

            async def is_alive(self):
                raise RuntimeError("network error")

            async def connect(self, force=False):
                pass

        tool = MCPTools()
        result = await tm.connect_and_get_tools([tool])
        assert tool not in result

    @pytest.mark.asyncio
    async def test_mcp_tool_build_tools_exception_skips_tool(self):
        tm = ToolManager(model=make_model())

        class MCPTools:
            initialized = True
            refresh_connection = True

            async def is_alive(self):
                return True

            async def connect(self, force=False):
                pass

            async def build_tools(self):
                raise RuntimeError("build failed")

        tool = MCPTools()
        result = await tm.connect_and_get_tools([tool])
        assert tool not in result

    @pytest.mark.asyncio
    async def test_mcp_tool_skip_check_includes_uninitialized(self):
        """When check_mcp_tools=False, uninitialized MCP tools are included."""
        tm = ToolManager(model=make_model())

        class MCPTools:
            initialized = False
            refresh_connection = False

        tool = MCPTools()
        result = await tm.connect_and_get_tools([tool], check_mcp_tools=False)
        assert tool in result


# ---------------------------------------------------------------------------
# ToolManager.determine_tools_for_model deep tests
# ---------------------------------------------------------------------------

class TestDetermineToolsForModelDeep:
    def _make_tm(self) -> ToolManager:
        return ToolManager(model=make_model())

    def test_processes_toolkit_tools(self):
        from ii_agent.agent.runtime.tools import Toolkit
        from ii_agent.agent.runtime.tools.function import Function

        tm = self._make_tm()
        run_output = make_run_output()
        session = make_session()
        run_context = MagicMock()

        # Create a mock toolkit
        toolkit = MagicMock(spec=Toolkit)
        toolkit.name = "my_toolkit"
        toolkit.add_instructions = False
        toolkit.instructions = None

        func1 = MagicMock(spec=Function)
        func1.name = "tool_one"
        func1.entrypoint = None
        func1.add_instructions = False
        func1.instructions = None
        func1.model_copy.return_value = func1
        func1.process_entrypoint = MagicMock()

        toolkit.functions = {"tool_one": func1}

        result = tm.determine_tools_for_model(
            processed_tools=[toolkit],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        assert func1 in result

    def test_processes_function_tools(self):
        from ii_agent.agent.runtime.tools.function import Function

        tm = self._make_tm()
        run_output = make_run_output()
        session = make_session()
        run_context = MagicMock()

        func = Function(name="direct_function")
        func.add_instructions = False
        func.instructions = None

        result = tm.determine_tools_for_model(
            processed_tools=[func],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        assert any(
            isinstance(f, Function) and f.name == "direct_function"
            for f in result
        )

    def test_skips_duplicate_function_tools(self):
        from ii_agent.agent.runtime.tools.function import Function

        tm = self._make_tm()
        run_output = make_run_output()
        session = make_session()
        run_context = MagicMock()

        func1 = Function(name="duplicate_tool")
        func1.add_instructions = False
        func1.instructions = None
        func2 = Function(name="duplicate_tool")  # Same name
        func2.add_instructions = False
        func2.instructions = None

        result = tm.determine_tools_for_model(
            processed_tools=[func1, func2],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        # Only one should be included
        names = [f.name if isinstance(f, Function) else None for f in result]
        assert names.count("duplicate_tool") == 1

    def test_skips_duplicate_toolkit_tools(self):
        from ii_agent.agent.runtime.tools import Toolkit
        from ii_agent.agent.runtime.tools.function import Function

        tm = self._make_tm()
        run_output = make_run_output()
        session = make_session()
        run_context = MagicMock()

        toolkit1 = MagicMock(spec=Toolkit)
        toolkit1.name = "toolkit1"
        toolkit1.add_instructions = False
        toolkit1.instructions = None
        func = MagicMock(spec=Function)
        func.name = "shared_tool"
        func.entrypoint = None
        func.add_instructions = False
        func.instructions = None
        func.model_copy.return_value = func
        func.process_entrypoint = MagicMock()
        toolkit1.functions = {"shared_tool": func}

        toolkit2 = MagicMock(spec=Toolkit)
        toolkit2.name = "toolkit2"
        toolkit2.add_instructions = False
        toolkit2.instructions = None
        func2 = MagicMock(spec=Function)
        func2.name = "shared_tool"  # Same name as in toolkit1
        func2.entrypoint = None
        func2.add_instructions = False
        func2.instructions = None
        func2.model_copy.return_value = func2
        func2.process_entrypoint = MagicMock()
        toolkit2.functions = {"shared_tool": func2}

        result = tm.determine_tools_for_model(
            processed_tools=[toolkit1, toolkit2],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        # shared_tool should only appear once
        func_names = [f.name if hasattr(f, "name") else None for f in result]
        assert func_names.count("shared_tool") == 1

    def test_tool_instructions_collected_from_base_agent_tools(self):
        from ii_agent.agent.runtime.tools.base import BaseAgentTool
        from ii_agent.agent.runtime.tools.function import Function

        tm = self._make_tm()
        run_output = make_run_output()
        session = make_session()
        run_context = MagicMock()

        tool = MagicMock(spec=BaseAgentTool)
        tool.name = "instructed_tool"
        tool.add_instructions = True
        tool.instructions = "Always use this tool with care."

        mock_func = MagicMock(spec=Function)
        mock_func.name = "instructed_tool"
        mock_func.entrypoint = None
        mock_func.add_instructions = False
        mock_func.model_copy.return_value = mock_func

        with patch.object(Function, "from_tool", return_value=mock_func), \
             patch.object(mock_func, "process_entrypoint"):
            tm.determine_tools_for_model(
                processed_tools=[tool],
                tool_hooks=None,
                run_response=run_output,
                run_context=run_context,
                session=session,
            )
        assert "Always use this tool with care." in tm.tool_instructions

    def test_applies_tool_hooks_to_toolkit_functions(self):
        from ii_agent.agent.runtime.tools import Toolkit
        from ii_agent.agent.runtime.tools.function import Function

        tm = self._make_tm()
        run_output = make_run_output()
        session = make_session()
        run_context = MagicMock()

        toolkit = MagicMock(spec=Toolkit)
        toolkit.name = "toolkit"
        toolkit.add_instructions = False
        toolkit.instructions = None
        func = MagicMock(spec=Function)
        func.name = "hooked_tool"
        func.entrypoint = None
        func.add_instructions = False
        func.instructions = None
        func.model_copy.return_value = func
        func.process_entrypoint = MagicMock()
        toolkit.functions = {"hooked_tool": func}

        hook = MagicMock()

        tm.determine_tools_for_model(
            processed_tools=[toolkit],
            tool_hooks=[hook],
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        # Tool hooks should be set on the function copy
        assert func.tool_hooks == [hook]

    def test_function_with_media_parameters_sets_media_on_func(self):
        from ii_agent.agent.runtime.tools.function import Function
        from ii_agent.agent.runtime.media import Image

        tm = self._make_tm()

        img = Image(id="img-1", url="http://example.com/img.png")
        run_output = make_run_output()
        run_output.input = RunInput(input_content="test", images=[img])
        session = make_session()
        run_context = MagicMock()

        def func_with_images(query: str, images) -> str:
            """Tool that uses images."""
            return query

        func = Function(name="image_tool")
        func.entrypoint = func_with_images
        func.add_instructions = False
        func.instructions = None

        result = tm.determine_tools_for_model(
            processed_tools=[func],
            tool_hooks=None,
            run_response=run_output,
            run_context=run_context,
            session=session,
        )
        # Should have set _images on the function
        if result:
            result_func = result[0]
            if isinstance(result_func, Function):
                assert result_func._images is not None


# ---------------------------------------------------------------------------
# await_for_thread_tasks_stream deep tests
# ---------------------------------------------------------------------------

class TestAwaitForThreadTasksStreamDeep:
    @pytest.mark.asyncio
    async def test_memory_task_yields_started_and_completed_events_when_streaming(self):
        from ii_agent.agent.runtime.utils.agent import await_for_thread_tasks_stream

        run_output = make_run_output()

        async def noop():
            pass

        memory_task = asyncio.ensure_future(noop())

        events = []
        async for event in await_for_thread_tasks_stream(
            run_response=run_output,
            memory_task=memory_task,
            stream_events=True,
        ):
            events.append(event)

        # Should have MemoryUpdateStarted and MemoryUpdateCompleted events
        event_types = [ev.event for ev in events]
        assert any("MemoryUpdate" in et for et in event_types)

    @pytest.mark.asyncio
    async def test_memory_task_exception_handled_gracefully(self):
        from ii_agent.agent.runtime.utils.agent import await_for_thread_tasks_stream

        run_output = make_run_output()

        async def failing_task():
            raise RuntimeError("memory failure")

        task = asyncio.ensure_future(failing_task())

        events = []
        async for event in await_for_thread_tasks_stream(
            run_response=run_output,
            memory_task=task,
            stream_events=False,
        ):
            events.append(event)
        # Should not raise

    @pytest.mark.asyncio
    async def test_no_tasks_yields_nothing(self):
        from ii_agent.agent.runtime.utils.agent import await_for_thread_tasks_stream

        run_output = make_run_output()
        events = []
        async for event in await_for_thread_tasks_stream(
            run_response=run_output,
            memory_task=None,
            stream_events=True,
        ):
            events.append(event)
        assert events == []

    @pytest.mark.asyncio
    async def test_cultural_knowledge_task_handled(self):
        from ii_agent.agent.runtime.utils.agent import await_for_thread_tasks_stream

        run_output = make_run_output()

        async def cultural_task():
            pass

        task = asyncio.ensure_future(cultural_task())

        events = []
        async for event in await_for_thread_tasks_stream(
            run_response=run_output,
            cultural_knowledge_task=task,
            stream_events=False,
        ):
            events.append(event)
        # Should complete without error

    @pytest.mark.asyncio
    async def test_cultural_knowledge_task_exception_handled(self):
        from ii_agent.agent.runtime.utils.agent import await_for_thread_tasks_stream

        run_output = make_run_output()

        async def failing_cultural():
            raise ValueError("cultural failure")

        task = asyncio.ensure_future(failing_cultural())

        events = []
        async for event in await_for_thread_tasks_stream(
            run_response=run_output,
            cultural_knowledge_task=task,
            stream_events=False,
        ):
            events.append(event)
        # Should not raise


# ---------------------------------------------------------------------------
# wait_for_thread_tasks_stream (sync Future version)
# ---------------------------------------------------------------------------

class TestWaitForThreadTasksStreamDeep:
    def test_memory_future_yields_events_when_streaming(self):
        from asyncio import Future
        from ii_agent.agent.runtime.utils.agent import wait_for_thread_tasks_stream

        run_output = make_run_output()
        future = Future()
        future.set_result(None)

        events = list(wait_for_thread_tasks_stream(
            run_response=run_output,
            memory_future=future,
            stream_events=True,
        ))
        event_types = [ev.event for ev in events]
        assert any("MemoryUpdate" in et for et in event_types)

    def test_memory_future_exception_handled(self):
        from asyncio import Future
        from ii_agent.agent.runtime.utils.agent import wait_for_thread_tasks_stream

        run_output = make_run_output()
        future = Future()
        future.set_exception(RuntimeError("memory fail"))

        events = list(wait_for_thread_tasks_stream(
            run_response=run_output,
            memory_future=future,
            stream_events=False,
        ))
        # Should not raise

    def test_cultural_future_exception_handled(self):
        from asyncio import Future
        from ii_agent.agent.runtime.utils.agent import wait_for_thread_tasks_stream

        run_output = make_run_output()
        cultural_future = Future()
        cultural_future.set_exception(ValueError("cultural fail"))

        events = list(wait_for_thread_tasks_stream(
            run_response=run_output,
            cultural_knowledge_future=cultural_future,
            stream_events=False,
        ))
        # Should not raise

    def test_no_futures_yields_nothing(self):
        from ii_agent.agent.runtime.utils.agent import wait_for_thread_tasks_stream

        run_output = make_run_output()
        events = list(wait_for_thread_tasks_stream(
            run_response=run_output,
            stream_events=True,
        ))
        assert events == []


# ---------------------------------------------------------------------------
# factory/converter.py - RunPausedEvent with tools and requirements
# ---------------------------------------------------------------------------

class TestConverterRunPausedDeep:
    SESSION_STR = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def _convert(self, event):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        return convert_agent_event_to_realtime(event, self.SESSION_STR)

    def test_paused_with_tools_includes_tool_data(self):
        from ii_agent.agent.runtime.run.agent import RunPausedEvent

        tool = MagicMock()
        tool.tool_call_id = "tc-001"
        tool.tool_name = "confirm_tool"
        tool.tool_args = {"key": "val"}
        tool.requires_confirmation = True
        tool.requires_user_input = False
        tool.external_execution_required = False
        tool.user_input_schema = None

        ev = RunPausedEvent(
            agent_id="a1",
            agent_name="A",
            tools=[tool],
            requirements=None,
        )
        realtime = self._convert(ev)
        assert len(realtime.content["tools"]) == 1
        assert realtime.content["tools"][0]["tool_call_id"] == "tc-001"

    def test_paused_with_requirements_includes_req_data(self):
        from ii_agent.agent.runtime.run.agent import RunPausedEvent

        req = MagicMock()
        req.id = "req-001"
        req.needs_confirmation = True
        req.needs_user_input = False
        req.needs_external_execution = False
        req.is_resolved.return_value = False
        req.tool_execution = MagicMock()
        req.tool_execution.tool_call_id = "tc-001"
        req.tool_execution.tool_name = "my_tool"
        req.tool_execution.tool_args = {}
        req.tool_execution.requires_confirmation = True
        req.tool_execution.requires_user_input = False
        req.tool_execution.external_execution_required = False
        req.tool_execution.user_input_schema = None

        ev = RunPausedEvent(
            agent_id="a1",
            agent_name="A",
            tools=None,
            requirements=[req],
        )
        realtime = self._convert(ev)
        assert len(realtime.content["requirements"]) == 1

    def test_paused_with_user_input_schema_in_tool(self):
        from ii_agent.agent.runtime.run.agent import RunPausedEvent
        from ii_agent.agent.runtime.tools.base import UserInputField

        tool = MagicMock()
        tool.tool_call_id = "tc-002"
        tool.tool_name = "user_input_tool"
        tool.tool_args = {}
        tool.requires_confirmation = False
        tool.requires_user_input = True
        tool.external_execution_required = False
        user_field = MagicMock(spec=UserInputField)
        user_field.to_dict.return_value = {"name": "target", "type": "string"}
        tool.user_input_schema = [user_field]

        ev = RunPausedEvent(
            agent_id="a1",
            agent_name="A",
            tools=[tool],
            requirements=None,
        )
        realtime = self._convert(ev)
        assert "user_input_schema" in realtime.content["tools"][0]


# ---------------------------------------------------------------------------
# factory/converter.py - ToolCallStarted/Completed events
# ---------------------------------------------------------------------------

class TestConverterToolCallEventsDeep:
    SESSION_STR = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    RUN_ID = "11111111-2222-3333-4444-555555555555"

    def _make_tool_started(self, tool=None):
        from ii_agent.agent.runtime.run.agent import ToolCallStartedEvent
        return ToolCallStartedEvent(
            agent_id="a1",
            agent_name="A",
            run_id=self.RUN_ID,
            tool=tool,
        )

    def _make_tool_completed(self, tool=None):
        from ii_agent.agent.runtime.run.agent import ToolCallCompletedEvent
        return ToolCallCompletedEvent(
            agent_id="a1",
            agent_name="A",
            run_id=self.RUN_ID,
            tool=tool,
        )

    def _convert(self, event):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        return convert_agent_event_to_realtime(event, self.SESSION_STR)

    def test_tool_started_returns_tool_call_type(self):
        from ii_agent.core.events.models import EventType

        tool = MagicMock()
        tool.tool_call_id = "tc-001"
        tool.tool_name = "my_tool"
        tool.tool_args = {}
        tool.display_name = "My Tool"
        tool.tool_logo = None

        ev = self._make_tool_started(tool=tool)
        realtime = self._convert(ev)
        assert realtime.type == EventType.TOOL_CALL

    def test_tool_started_includes_tool_data(self):
        tool = MagicMock()
        tool.tool_call_id = "tc-001"
        tool.tool_name = "search_tool"
        tool.tool_args = {"query": "test"}
        tool.display_name = "Search"
        tool.tool_logo = "http://logo.example.com/search.png"

        ev = self._make_tool_started(tool=tool)
        realtime = self._convert(ev)
        assert realtime.content["tool_name"] == "search_tool"
        assert realtime.content["tool_logo"] == "http://logo.example.com/search.png"

    def test_tool_started_with_no_tool(self):
        ev = self._make_tool_started(tool=None)
        realtime = self._convert(ev)
        assert realtime is not None

    def test_tool_completed_returns_tool_result_type(self):
        from ii_agent.core.events.models import EventType

        tool = MagicMock()
        tool.tool_call_id = "tc-001"
        tool.tool_name = "my_tool"
        tool.tool_args = {}
        tool.display_name = "My Tool"
        tool.tool_logo = None
        tool.result = "Tool output"

        ev = self._make_tool_completed(tool=tool)
        realtime = self._convert(ev)
        assert realtime.type == EventType.TOOL_RESULT

    def test_tool_completed_with_tool_result_object(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = MagicMock()
        tool.tool_call_id = "tc-002"
        tool.tool_name = "my_tool"
        tool.tool_args = {}
        tool.display_name = "My Tool"
        tool.tool_logo = None
        tool_result = ToolResult(
            llm_content="llm text",
            user_display_content="display text",
            is_error=False,
        )
        tool.result = tool_result

        ev = self._make_tool_completed(tool=tool)
        realtime = self._convert(ev)
        assert realtime.content["result"] == "display text"

    def test_tool_completed_with_error_tool_result(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = MagicMock()
        tool.tool_call_id = "tc-003"
        tool.tool_name = "failing_tool"
        tool.tool_args = {}
        tool.display_name = "Failing"
        tool.tool_logo = None
        tool_result = ToolResult(
            llm_content="Error: something went wrong",
            user_display_content=None,
            is_error=True,
        )
        tool.result = tool_result

        ev = self._make_tool_completed(tool=tool)
        realtime = self._convert(ev)
        assert realtime.content["is_error"] is True

    def test_tool_completed_with_list_llm_content(self):
        from ii_agent.agent.runtime.tools.base import ToolResult, TextContent

        tool = MagicMock()
        tool.tool_call_id = "tc-004"
        tool.tool_name = "multi_tool"
        tool.tool_args = {}
        tool.display_name = "Multi"
        tool.tool_logo = None
        content_item = TextContent(type="text", text="item content")
        tool_result = ToolResult(
            llm_content=[content_item],
            user_display_content=None,
            is_error=False,
        )
        tool.result = tool_result

        ev = self._make_tool_completed(tool=tool)
        realtime = self._convert(ev)
        assert isinstance(realtime.content["result"], list)


# ---------------------------------------------------------------------------
# factory/converter.py - SandboxInitializedEvent
# ---------------------------------------------------------------------------

class TestConverterSandboxDeep:
    SESSION_STR = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    RUN_ID = "11111111-2222-3333-4444-555555555555"

    def test_sandbox_initialized_returns_sandbox_status_type(self):
        from ii_agent.agent.runtime.run.agent import SandboxInitializedEvent
        from ii_agent.core.events.models import EventType
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        sandbox_info = MagicMock()
        sandbox_info.status = "running"
        sandbox_info.vscode_url = "http://vscode.example.com"

        ev = SandboxInitializedEvent(
            agent_id="a1",
            agent_name="A",
            run_id=self.RUN_ID,
            sandbox_info=sandbox_info,
        )
        realtime = convert_agent_event_to_realtime(ev, self.SESSION_STR)
        assert realtime.type == EventType.SANDBOX_STATUS
        assert realtime.content["status"] == "running"
        assert realtime.content["vscode_url"] == "http://vscode.example.com"

    def test_sandbox_initialized_with_no_info(self):
        from ii_agent.agent.runtime.run.agent import SandboxInitializedEvent
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        ev = SandboxInitializedEvent(
            agent_id="a1",
            agent_name="A",
            run_id=self.RUN_ID,
            sandbox_info=None,
        )
        realtime = convert_agent_event_to_realtime(ev, self.SESSION_STR)
        assert realtime is not None
        assert realtime.content["status"] is None
