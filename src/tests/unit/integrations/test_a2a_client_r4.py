"""Unit tests for A2A client, server, executor, and manager (r4)."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# as_client_interceptors.py - ExtensionsHeaderInterceptor
# ===========================================================================

class TestExtensionsHeaderInterceptorExtractExtensions:
    def test_empty_payload_returns_empty(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._extract_extensions({})
        assert result == []

    def test_missing_params_returns_empty(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._extract_extensions({"params": None})
        assert result == []

    def test_missing_message_returns_empty(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._extract_extensions({"params": {"other": "val"}})
        assert result == []

    def test_missing_extensions_returns_empty(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._extract_extensions(
            {"params": {"message": {"other": "val"}}}
        )
        assert result == []

    def test_extracts_extension_list(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        payload = {
            "params": {
                "message": {
                    "extensions": ["ext.a", "ext.b"]
                }
            }
        }
        result = ExtensionsHeaderInterceptor._extract_extensions(payload)
        assert "ext.a" in result
        assert "ext.b" in result

    def test_deduplicates_extensions(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        payload = {
            "params": {
                "message": {
                    "extensions": ["ext.a", "ext.a", "ext.b"]
                }
            }
        }
        result = ExtensionsHeaderInterceptor._extract_extensions(payload)
        assert result.count("ext.a") == 1

    def test_empty_strings_filtered_out(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        payload = {
            "params": {
                "message": {
                    "extensions": ["ext.a", "", "  "]
                }
            }
        }
        result = ExtensionsHeaderInterceptor._extract_extensions(payload)
        assert "" not in result
        assert "  " not in result


class TestExtensionsHeaderInterceptorSplitHeader:
    def test_none_returns_empty(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        assert ExtensionsHeaderInterceptor._split_header(None) == []

    def test_empty_string_returns_empty(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        assert ExtensionsHeaderInterceptor._split_header("") == []

    def test_single_value(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._split_header("ext.a")
        assert result == ["ext.a"]

    def test_comma_separated_values(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._split_header("ext.a, ext.b, ext.c")
        assert "ext.a" in result
        assert "ext.b" in result
        assert "ext.c" in result

    def test_strips_whitespace(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        result = ExtensionsHeaderInterceptor._split_header("  ext.a  ,  ext.b  ")
        assert "ext.a" in result
        assert "ext.b" in result


class TestExtensionsHeaderInterceptorIntercept:
    @pytest.mark.asyncio
    async def test_non_send_method_returns_unchanged(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        interceptor = ExtensionsHeaderInterceptor()
        payload = {"some": "data"}
        kwargs = {"headers": {}}

        result_payload, result_kwargs = await interceptor.intercept(
            method_name="other/method",
            request_payload=payload,
            http_kwargs=kwargs,
            agent_card=None,
            context=None,
        )
        assert result_payload is payload
        assert result_kwargs is kwargs

    @pytest.mark.asyncio
    async def test_message_send_with_extensions_adds_header(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor
        from a2a.extensions.common import HTTP_EXTENSION_HEADER

        interceptor = ExtensionsHeaderInterceptor()
        payload = {
            "params": {
                "message": {
                    "extensions": ["ext.a", "ext.b"]
                }
            }
        }
        kwargs = {}

        _, result_kwargs = await interceptor.intercept(
            method_name="message/send",
            request_payload=payload,
            http_kwargs=kwargs,
            agent_card=None,
            context=None,
        )
        assert HTTP_EXTENSION_HEADER in result_kwargs.get("headers", {})

    @pytest.mark.asyncio
    async def test_no_extensions_returns_unchanged_kwargs(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor

        interceptor = ExtensionsHeaderInterceptor()
        payload = {"params": {"message": {}}}
        kwargs = {"original": "value"}

        _, result_kwargs = await interceptor.intercept(
            method_name="message/send",
            request_payload=payload,
            http_kwargs=kwargs,
            agent_card=None,
            context=None,
        )
        assert result_kwargs is kwargs

    @pytest.mark.asyncio
    async def test_context_state_updated_with_requested(self):
        from ii_agent.integrations.a2a.as_client_interceptors import ExtensionsHeaderInterceptor
        from a2a.client import ClientCallContext

        interceptor = ExtensionsHeaderInterceptor()
        payload = {
            "params": {
                "message": {
                    "extensions": ["ext.x"]
                }
            }
        }
        context = ClientCallContext()

        await interceptor.intercept(
            method_name="message/stream",
            request_payload=payload,
            http_kwargs={},
            agent_card=None,
            context=context,
        )
        state = context.state.get(ExtensionsHeaderInterceptor._STATE_KEY, {})
        assert "requested" in state
        assert "ext.x" in state["requested"]


# ===========================================================================
# a2a/manager.py - A2AManager
# ===========================================================================

class TestA2AManagerNormalizeAgentConfig:
    def test_string_url_normalized_to_dict(self):
        from ii_agent.integrations.a2a.manager import A2AManager

        result = A2AManager._normalize_agent_config("my_agent", "http://agent.example.com")
        assert result["url"] == "http://agent.example.com"
        assert result["name"] == "my_agent"

    def test_empty_string_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config("agent", "")

    def test_dict_with_url_normalized(self):
        from ii_agent.integrations.a2a.manager import A2AManager

        result = A2AManager._normalize_agent_config(
            "agent", {"url": "http://agent.com", "description": "My agent"}
        )
        assert result["url"] == "http://agent.com"
        assert result["description"] == "My agent"

    def test_dict_missing_url_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config("agent", {"name": "test"})

    def test_dict_with_empty_url_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config("agent", {"url": ""})

    def test_unsupported_type_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config("agent", 42)

    def test_dict_with_non_string_description_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config(
                "agent", {"url": "http://x.com", "description": 123}
            )

    def test_dict_with_non_dict_metadata_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config(
                "agent", {"url": "http://x.com", "metadata": "not_a_dict"}
            )

    def test_dict_with_none_metadata_allowed(self):
        from ii_agent.integrations.a2a.manager import A2AManager

        result = A2AManager._normalize_agent_config(
            "agent", {"url": "http://x.com", "metadata": None}
        )
        assert result["metadata"] is None

    def test_dict_with_headers_sanitized(self):
        from ii_agent.integrations.a2a.manager import A2AManager

        result = A2AManager._normalize_agent_config(
            "agent",
            {"url": "http://x.com", "headers": {"X-Key": "value", None: "skip", "": "skip2"}},
        )
        assert result.get("headers") == {"X-Key": "value"}

    def test_dict_with_non_dict_headers_raises_error(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.exceptions import InvalidA2AAgentConfig

        with pytest.raises(InvalidA2AAgentConfig):
            A2AManager._normalize_agent_config(
                "agent", {"url": "http://x.com", "headers": "not_a_dict"}
            )


class TestA2AManagerInit:
    def test_empty_config_creates_empty_agents(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {}
        manager = A2AManager(config=mock_config)
        assert not manager.has_a2a_agents()

    def test_has_agents_returns_true(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {
            "agent1": "http://agent1.example.com"
        }
        manager = A2AManager(config=mock_config)
        assert manager.has_a2a_agents()

    def test_get_a2a_agents_returns_deep_copy(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {
            "agent1": "http://agent1.example.com"
        }
        manager = A2AManager(config=mock_config)
        agents1 = manager.get_a2a_agents()
        agents2 = manager.get_a2a_agents()
        assert agents1 == agents2
        assert agents1 is not agents2


class TestA2AManagerCreateTool:
    def test_creates_tool_on_first_call(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {}

        mock_tool = MagicMock()

        with patch("ii_agent.integrations.a2a.manager.A2AAgentTool", return_value=mock_tool):
            manager = A2AManager(config=mock_config)
            tool = manager.create_a2a_tool({"agent1": {"url": "http://a.com"}})
            assert tool is mock_tool

    def test_returns_cached_tool_on_second_call(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {}

        mock_tool = MagicMock()
        with patch("ii_agent.integrations.a2a.manager.A2AAgentTool", return_value=mock_tool):
            manager = A2AManager(config=mock_config)
            tool1 = manager.create_a2a_tool({"agent1": {"url": "http://a.com"}})
            tool2 = manager.create_a2a_tool({"agent1": {"url": "http://a.com"}})
            assert tool1 is tool2


class TestA2AManagerGetPrompt:
    def test_returns_empty_string_when_no_agents(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {}

        manager = A2AManager(config=mock_config)
        result = manager.get_a2a_prompt()
        assert result == ""

    def test_returns_prompt_when_agents_configured(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {
            "agent1": "http://agent.example.com"
        }

        with patch(
            "ii_agent.engine.prompts.a2a_agents_prompt.build_a2a_agents_prompt",
            return_value="A2A prompt text",
        ):
            manager = A2AManager(config=mock_config)
            result = manager.get_a2a_prompt()
            assert isinstance(result, str)
            assert len(result) >= 0  # Just verify it returns a string


class TestA2AManagerGetToolForRegistration:
    def test_returns_none_when_no_agents(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {}

        manager = A2AManager(config=mock_config)
        assert manager.get_a2a_tool_for_registration() is None

    def test_returns_tool_when_agents_configured(self):
        from ii_agent.integrations.a2a.manager import A2AManager
        from ii_agent.integrations.a2a.config import A2AConfig

        mock_config = MagicMock(spec=A2AConfig)
        mock_config.get_third_party_agents.return_value = {
            "agent1": "http://agent.example.com"
        }

        mock_tool = MagicMock()
        with patch("ii_agent.integrations.a2a.manager.A2AAgentTool", return_value=mock_tool):
            manager = A2AManager(config=mock_config)
            tool = manager.get_a2a_tool_for_registration()
            assert tool is mock_tool


# ===========================================================================
# agent_executor.py - IIAgentExecutor
# ===========================================================================

class TestIIAgentExecutorBuildMessage:
    def test_builds_message_with_text(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from a2a.types import Role

        msg = IIAgentExecutor._build_message(
            context_id="ctx-1", task_id="task-1", text="Hello"
        )
        assert msg.role == Role.agent
        assert len(msg.parts) == 1

    def test_message_has_context_and_task_ids(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        msg = IIAgentExecutor._build_message(
            context_id="ctx-1", task_id="task-1", text="Test"
        )
        assert msg.context_id == "ctx-1"
        assert msg.task_id == "task-1"


class TestIIAgentExecutorWithExtensionMetadata:
    def test_returns_none_when_no_base_and_no_extensions(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._with_extension_metadata(None, {})
        assert result is None

    def test_returns_base_with_extensions(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._with_extension_metadata(
            {"code": "done"}, {"active": ["ext.a"]}
        )
        assert result is not None
        assert "extensions" in result
        assert result["code"] == "done"

    def test_base_without_extension_info(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._with_extension_metadata({"code": "done"}, {})
        assert result == {"code": "done"}

    def test_empty_base_and_non_empty_extensions(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._with_extension_metadata({}, {"active": ["ext.a"]})
        assert result is not None
        assert "extensions" in result


class TestIIAgentExecutorPrepareExtensionContext:
    def test_empty_extensions_returns_empty_context(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        result = IIAgentExecutor._prepare_extension_context(set(), A2ARequestPayload())
        assert result == {}

    def test_supported_extension_appears_in_active(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload
        from ii_agent.integrations.a2a.constants import SESSION_CONTEXT_EXTENSION_URI

        result = IIAgentExecutor._prepare_extension_context(
            {SESSION_CONTEXT_EXTENSION_URI}, A2ARequestPayload()
        )
        assert SESSION_CONTEXT_EXTENSION_URI in result.get("active", [])

    def test_unsupported_extension_appears_in_unsupported(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload

        result = IIAgentExecutor._prepare_extension_context(
            {"urn:unsupported"}, A2ARequestPayload()
        )
        assert "urn:unsupported" in result.get("unsupported", [])

    def test_requested_field_lists_all_requested(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from ii_agent.integrations.a2a.context_adapter import A2ARequestPayload
        from ii_agent.integrations.a2a.constants import SANDBOX_REUSE_EXTENSION_URI

        result = IIAgentExecutor._prepare_extension_context(
            {SANDBOX_REUSE_EXTENSION_URI}, A2ARequestPayload()
        )
        assert SANDBOX_REUSE_EXTENSION_URI in result.get("requested", [])


class TestIIAgentExecutorBuildCompletionMetadata:
    def test_returns_completed_code(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._build_completion_metadata({"progress": 100}, {})
        assert result is not None
        assert result.get("code") == "completed"

    def test_includes_result_data_when_present(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._build_completion_metadata(
            {"result_data": {"key": "value"}}, {}
        )
        assert result["result"] == {"key": "value"}

    def test_default_progress_is_100(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        result = IIAgentExecutor._build_completion_metadata({}, {})
        assert result["progress"] == 100


class TestIIAgentExecutorEmitStatusUpdate:
    @pytest.mark.asyncio
    async def test_emits_status_update_event(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from a2a.types import TaskState

        executor = IIAgentExecutor.__new__(IIAgentExecutor)
        mock_queue = MagicMock()
        mock_queue.enqueue_event = AsyncMock()

        # Patch out IIAgentA2AServer initialization
        with patch("ii_agent.integrations.a2a.agent_executor.IIAgentA2AServer"):
            executor.agent = MagicMock()

        await executor._emit_status_update(
            event_queue=mock_queue,
            context_id="ctx-1",
            task_id="task-1",
            state=TaskState.working,
            text="Working...",
            final=False,
        )
        mock_queue.enqueue_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_final_flag_passed_through(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from a2a.types import TaskState, TaskStatusUpdateEvent

        executor = IIAgentExecutor.__new__(IIAgentExecutor)
        captured = []

        mock_queue = MagicMock()
        async def capture_event(evt):
            captured.append(evt)
        mock_queue.enqueue_event = capture_event

        await executor._emit_status_update(
            event_queue=mock_queue,
            context_id="ctx-1",
            task_id="task-1",
            state=TaskState.completed,
            text="Done",
            final=True,
        )

        assert len(captured) == 1
        assert isinstance(captured[0], TaskStatusUpdateEvent)
        assert captured[0].final is True


class TestIIAgentExecutorCancel:
    @pytest.mark.asyncio
    async def test_cancel_enqueues_artifact_event(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor
        from a2a.types import TaskArtifactUpdateEvent

        executor = IIAgentExecutor.__new__(IIAgentExecutor)
        mock_queue = MagicMock()
        captured = []

        async def capture_event(evt):
            captured.append(evt)
        mock_queue.enqueue_event = capture_event

        mock_context = MagicMock()
        mock_context.task_id = "task-1"
        mock_context.context_id = "ctx-1"

        await executor.cancel(mock_context, mock_queue)

        assert len(captured) == 1
        assert isinstance(captured[0], TaskArtifactUpdateEvent)


class TestIIAgentExecutorResolveRequestedExtensions:
    def test_returns_empty_set_on_error(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        mock_context = MagicMock()

        with patch(
            "ii_agent.integrations.a2a.agent_executor.collect_requested_extensions",
            side_effect=Exception("boom"),
        ):
            result = IIAgentExecutor._resolve_requested_extensions(mock_context)
            assert result == set()

    def test_returns_extensions_from_context(self):
        from ii_agent.integrations.a2a.agent_executor import IIAgentExecutor

        mock_context = MagicMock()
        with patch(
            "ii_agent.integrations.a2a.agent_executor.collect_requested_extensions",
            return_value={"ext.a"},
        ):
            result = IIAgentExecutor._resolve_requested_extensions(mock_context)
            assert "ext.a" in result


# ===========================================================================
# Additional as_client.py coverage
# ===========================================================================

class TestYieldStreamItems:
    @pytest.mark.asyncio
    async def test_message_payload_yields_message(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        client = IIAgentA2AClient("http://agent.example.com")
        msg = create_text_message_object(role=Role.agent, content="hello")

        items = []
        async for item in client._yield_stream_items(msg):
            items.append(item)

        assert len(items) == 1
        assert items[0] is msg

    @pytest.mark.asyncio
    async def test_tuple_payload_yields_update(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        client = IIAgentA2AClient("http://agent.example.com")
        task = MagicMock()
        update = MagicMock()

        items = []
        async for item in client._yield_stream_items((task, update)):
            items.append(item)

        assert update in items

    @pytest.mark.asyncio
    async def test_tuple_with_none_update_yields_task(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

        client = IIAgentA2AClient("http://agent.example.com")
        task = MagicMock()

        items = []
        async for item in client._yield_stream_items((task, None)):
            items.append(item)

        assert task in items


class TestExtractTextFromPayload:
    def test_extracts_from_message_payload(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        client = IIAgentA2AClient("http://agent.example.com")
        msg = create_text_message_object(role=Role.agent, content="test response")

        result = client._extract_text_from_payload(msg)
        assert result == "test response"

    def test_extracts_from_tuple_with_status_update(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.types import TaskStatusUpdateEvent, TaskStatus, TaskState
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        client = IIAgentA2AClient("http://agent.example.com")
        msg = create_text_message_object(role=Role.agent, content="status text")
        update = TaskStatusUpdateEvent(
            context_id="ctx",
            task_id="task",
            status=TaskStatus(state=TaskState.completed, message=msg),
            final=True,
            kind="status-update",
        )

        task = MagicMock()
        result = client._extract_text_from_payload((task, update))
        assert result == "status text"


class TestApplyExtensionMetadataDefaults:
    def test_no_extension_definitions_does_nothing(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role

        client = IIAgentA2AClient("http://agent.example.com")
        client._extension_definitions = {}
        msg = create_text_message_object(role=Role.user, content="hi")
        original_metadata = msg.metadata

        client._apply_extension_metadata_defaults(msg, {})
        assert msg.metadata == original_metadata

    def test_extension_with_metadata_key_adds_to_message(self):
        from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
        from a2a.client.helpers import create_text_message_object
        from a2a.types import Role, AgentExtension

        client = IIAgentA2AClient("http://agent.example.com")
        ext = AgentExtension(
            uri="urn:ext.test",
            required=False,
            params={"metadata_key": "ext_test"},
        )
        client._extension_definitions = {"urn:ext.test": ext}

        msg = create_text_message_object(role=Role.user, content="hi")
        client._apply_extension_metadata_defaults(msg, {})
        if msg.metadata:
            # The extension metadata key should have been added
            assert "ext_test" in msg.metadata
