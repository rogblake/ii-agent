"""
Deep unit tests for ii_agent/engine/runtime/models/base.py

Covers previously untested branches:
- MessageData dataclass
- _handle_agent_exception utility function
- Model.to_dict()
- Model.get_provider()
- Model._format_tools()
- Model._get_retry_delay() with and without exponential backoff
- Model._ainvoke_with_retry() - success, retry, and exhaust retries
- Model._ainvoke_stream_with_retry() - success, retry, and exhaust retries
- Model.aresponse() - basic happy path (no tool calls)
- Model._populate_assistant_message()
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.engine.runtime.models.base import MessageData, Model, _handle_agent_exception
from ii_agent.engine.runtime.models.message import Message
from ii_agent.engine.runtime.models.metrics import Metrics
from ii_agent.engine.runtime.models.response import ModelResponse
from ii_agent.engine.runtime.exceptions import AgentRunException, ModelProviderError
from ii_agent.engine.runtime.tools.function import Function


# ---------------------------------------------------------------------------
# Concrete test subclass (since Model is abstract)
# ---------------------------------------------------------------------------

@dataclass
class _ConcreteModel(Model):
    id: str = "test-model"

    async def ainvoke(self, *args, **kwargs) -> ModelResponse:
        return ModelResponse(role="assistant", content="ok")

    async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
        yield ModelResponse(role="assistant", content="streaming")

    def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
        return ModelResponse(role="assistant", content=str(response))

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        return ModelResponse(role="assistant", content=str(response), is_delta=True)


# ---------------------------------------------------------------------------
# MessageData tests
# ---------------------------------------------------------------------------

class TestMessageData:
    def test_default_response_role_is_none(self):
        md = MessageData()
        assert md.response_role is None

    def test_default_response_content_is_empty_string(self):
        md = MessageData()
        assert md.response_content == ""

    def test_default_reasoning_content_is_empty_string(self):
        md = MessageData()
        assert md.response_reasoning_content == ""

    def test_default_redacted_reasoning_is_empty_string(self):
        md = MessageData()
        assert md.response_redacted_reasoning_content == ""

    def test_default_citations_is_none(self):
        md = MessageData()
        assert md.response_citations is None

    def test_default_tool_calls_is_empty_list(self):
        md = MessageData()
        assert md.response_tool_calls == []

    def test_default_audio_is_none(self):
        md = MessageData()
        assert md.response_audio is None

    def test_default_image_is_none(self):
        md = MessageData()
        assert md.response_image is None

    def test_default_metrics_is_none(self):
        md = MessageData()
        assert md.response_metrics is None

    def test_default_provider_data_is_none(self):
        md = MessageData()
        assert md.response_provider_data is None

    def test_default_extra_is_none(self):
        md = MessageData()
        assert md.extra is None

    def test_set_role(self):
        md = MessageData(response_role="assistant")
        assert md.response_role == "assistant"

    def test_set_content(self):
        md = MessageData(response_content="Hello world")
        assert md.response_content == "Hello world"

    def test_tool_calls_list_independent_per_instance(self):
        md1 = MessageData()
        md2 = MessageData()
        md1.response_tool_calls.append("tool_1")
        assert md2.response_tool_calls == []


# ---------------------------------------------------------------------------
# _handle_agent_exception tests
# ---------------------------------------------------------------------------

class TestHandleAgentException:
    def test_user_message_string_creates_user_message(self):
        exc = AgentRunException("exc", user_message="user msg")
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert len(additional) == 1
        assert additional[0].role == "user"
        assert additional[0].content == "user msg"

    def test_user_message_message_object_appended_directly(self):
        user_msg = Message(role="user", content="prebuilt")
        exc = AgentRunException("exc", user_message=user_msg)
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert len(additional) == 1
        assert additional[0] is user_msg

    def test_agent_message_string_creates_assistant_message(self):
        exc = AgentRunException("exc", agent_message="assistant says hi")
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert len(additional) == 1
        assert additional[0].role == "assistant"
        assert additional[0].content == "assistant says hi"

    def test_agent_message_message_object_appended_directly(self):
        agent_msg = Message(role="assistant", content="prebuilt")
        exc = AgentRunException("exc", agent_message=agent_msg)
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert len(additional) == 1
        assert additional[0] is agent_msg

    def test_messages_list_of_message_objects_appended(self):
        msg1 = Message(role="user", content="m1")
        msg2 = Message(role="user", content="m2")
        exc = AgentRunException("exc", messages=[msg1, msg2])
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert len(additional) == 2

    def test_messages_list_of_dicts_converted_to_messages(self):
        exc = AgentRunException("exc", messages=[{"role": "user", "content": "dict msg"}])
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert len(additional) == 1
        assert additional[0].role == "user"

    def test_invalid_dict_message_logged_as_warning(self):
        exc = AgentRunException("exc", messages=[{"invalid_field": "no role"}])
        additional: List[Message] = []
        # Should not raise - logs warning instead
        _handle_agent_exception(exc, additional)

    def test_stop_execution_sets_stop_after_tool_call(self):
        exc = AgentRunException(
            "exc",
            user_message="stop please",
            stop_execution=True,
        )
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        for m in additional:
            assert m.stop_after_tool_call is True

    def test_no_stop_execution_does_not_set_stop_after_tool_call(self):
        exc = AgentRunException("exc", user_message="keep going")
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        for m in additional:
            assert m.stop_after_tool_call is False

    def test_none_additional_input_creates_list(self):
        exc = AgentRunException("exc", user_message="hello")
        # Pass None to trigger default creation
        _handle_agent_exception(exc, None)

    def test_both_user_and_agent_messages(self):
        exc = AgentRunException(
            "exc",
            user_message="user says",
            agent_message="agent says",
        )
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        roles = [m.role for m in additional]
        assert "user" in roles
        assert "assistant" in roles

    def test_no_messages_no_user_no_agent_produces_empty(self):
        exc = AgentRunException("exc")
        additional: List[Message] = []
        _handle_agent_exception(exc, additional)
        assert additional == []


# ---------------------------------------------------------------------------
# Model.to_dict() and get_provider() tests
# ---------------------------------------------------------------------------

class TestModelToDict:
    def test_returns_dict(self):
        m = _ConcreteModel(id="my-model", name="TestModel")
        d = m.to_dict()
        assert isinstance(d, dict)

    def test_includes_name(self):
        m = _ConcreteModel(id="my-model", name="TestModel")
        assert m.to_dict()["name"] == "TestModel"

    def test_includes_id(self):
        m = _ConcreteModel(id="my-model", name="TestModel")
        assert m.to_dict()["id"] == "my-model"

    def test_excludes_none_fields(self):
        m = _ConcreteModel(id="my-model", name=None)
        d = m.to_dict()
        assert "name" not in d

    def test_get_provider_returns_provider_when_set(self):
        from ii_agent.engine.types import Provider
        m = _ConcreteModel(id="gpt-4", name="Test", provider=Provider.OPENAI)
        assert m.get_provider() == Provider.OPENAI

    def test_get_provider_falls_back_to_name(self):
        # When provider is None and name is set, __post_init__ sets provider = "Name (id)"
        m = _ConcreteModel(id="gpt-4", name="MyModel", provider=None)
        # Provider is set by __post_init__ to "MyModel (gpt-4)"
        provider = m.get_provider()
        assert "MyModel" in provider

    def test_get_provider_falls_back_to_class_name(self):
        # When provider=None and name=None, __post_init__ does not set provider (name is None)
        m = _ConcreteModel(id="gpt-4", name=None, provider=None)
        # provider stays None, name is None, so falls back to class name
        assert m.get_provider() == "_ConcreteModel"


# ---------------------------------------------------------------------------
# Model._format_tools() tests
# ---------------------------------------------------------------------------

class TestModelFormatTools:
    def test_none_tools_returns_empty_list(self):
        m = _ConcreteModel()
        assert m._format_tools(None) == []

    def test_empty_list_returns_empty_list(self):
        m = _ConcreteModel()
        assert m._format_tools([]) == []

    def test_function_object_wrapped_in_type_function(self):
        m = _ConcreteModel()
        fn = MagicMock(spec=Function)
        fn.name = "search"
        fn.to_dict.return_value = {"name": "search", "description": "Search"}
        result = m._format_tools([fn])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "search"

    def test_dict_tool_passed_through_unchanged(self):
        m = _ConcreteModel()
        tool_dict = {"type": "web_search"}
        result = m._format_tools([tool_dict])
        assert result == [tool_dict]

    def test_mixed_tools_function_and_dict(self):
        m = _ConcreteModel()
        fn = MagicMock(spec=Function)
        fn.to_dict.return_value = {"name": "fn_a"}
        dict_tool = {"type": "builtin_tool"}
        result = m._format_tools([fn, dict_tool])
        assert len(result) == 2
        # fn should be wrapped
        assert result[0]["type"] == "function"
        # dict passed through
        assert result[1] == dict_tool


# ---------------------------------------------------------------------------
# Model._get_retry_delay() tests
# ---------------------------------------------------------------------------

class TestModelGetRetryDelay:
    def test_linear_delay_returns_constant(self):
        m = _ConcreteModel(delay_between_retries=5, exponential_backoff=False)
        assert m._get_retry_delay(0) == 5
        assert m._get_retry_delay(1) == 5
        assert m._get_retry_delay(3) == 5

    def test_exponential_backoff_doubles_delay(self):
        m = _ConcreteModel(delay_between_retries=2, exponential_backoff=True)
        assert m._get_retry_delay(0) == 2 * (2 ** 0)  # 2
        assert m._get_retry_delay(1) == 2 * (2 ** 1)  # 4
        assert m._get_retry_delay(2) == 2 * (2 ** 2)  # 8
        assert m._get_retry_delay(3) == 2 * (2 ** 3)  # 16

    def test_default_delay_is_one(self):
        m = _ConcreteModel()
        assert m._get_retry_delay(0) == 1


# ---------------------------------------------------------------------------
# Model._ainvoke_with_retry() tests
# ---------------------------------------------------------------------------

class TestAInvokeWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try_returns_response(self):
        m = _ConcreteModel(retries=2)
        result = await m._ainvoke_with_retry(
            messages=[Message(role="user", content="hi")],
            assistant_message=Message(role="assistant"),
        )
        assert isinstance(result, ModelResponse)
        assert result.content == "ok"

    @pytest.mark.asyncio
    async def test_retries_on_model_provider_error(self):
        call_count = 0

        @dataclass
        class _RetryModel(Model):
            id: str = "retry-model"

            async def ainvoke(self, *args, **kwargs) -> ModelResponse:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ModelProviderError("transient error", model_name="retry-model")
                return ModelResponse(role="assistant", content="success after retry")

            async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
                yield ModelResponse(role="assistant", content="stream")

            def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
                return ModelResponse()

            def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
                return ModelResponse()

        m = _RetryModel(retries=2, delay_between_retries=0)
        result = await m._ainvoke_with_retry(
            messages=[Message(role="user", content="test")],
            assistant_message=Message(role="assistant"),
        )
        assert result.content == "success after retry"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_raises(self):
        @dataclass
        class _AlwaysFailModel(Model):
            id: str = "fail-model"

            async def ainvoke(self, *args, **kwargs) -> ModelResponse:
                raise ModelProviderError("always fails", model_name="fail-model")

            async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
                raise ModelProviderError("stream fail", model_name="fail-model")
                yield  # make it a generator

            def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
                return ModelResponse()

            def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
                return ModelResponse()

        m = _AlwaysFailModel(retries=2, delay_between_retries=0)
        with pytest.raises(ModelProviderError):
            await m._ainvoke_with_retry(
                messages=[Message(role="user", content="test")],
                assistant_message=Message(role="assistant"),
            )

    @pytest.mark.asyncio
    async def test_zero_retries_raises_immediately(self):
        @dataclass
        class _ZeroRetryModel(Model):
            id: str = "zero-retry"

            async def ainvoke(self, *args, **kwargs) -> ModelResponse:
                raise ModelProviderError("fail", model_name="zero-retry")

            async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
                yield ModelResponse()

            def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
                return ModelResponse()

            def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
                return ModelResponse()

        m = _ZeroRetryModel(retries=0, delay_between_retries=0)
        with pytest.raises(ModelProviderError):
            await m._ainvoke_with_retry(
                messages=[Message(role="user", content="test")],
                assistant_message=Message(role="assistant"),
            )


# ---------------------------------------------------------------------------
# Model._ainvoke_stream_with_retry() tests
# ---------------------------------------------------------------------------

class TestAInvokeStreamWithRetry:
    @pytest.mark.asyncio
    async def test_success_yields_responses(self):
        m = _ConcreteModel(retries=0)
        responses = []
        async for r in m._ainvoke_stream_with_retry(
            messages=[Message(role="user", content="hi")],
            assistant_message=Message(role="assistant"),
        ):
            responses.append(r)
        assert len(responses) == 1
        assert responses[0].content == "streaming"

    @pytest.mark.asyncio
    async def test_stream_retries_on_provider_error(self):
        call_count = 0

        @dataclass
        class _RetryStreamModel(Model):
            id: str = "retry-stream"

            async def ainvoke(self, *args, **kwargs) -> ModelResponse:
                return ModelResponse()

            async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ModelProviderError("stream error", model_name="retry-stream")
                yield ModelResponse(role="assistant", content="stream success")

            def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
                return ModelResponse()

            def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
                return ModelResponse()

        m = _RetryStreamModel(retries=2, delay_between_retries=0)
        responses = []
        async for r in m._ainvoke_stream_with_retry(
            messages=[Message(role="user", content="test")],
            assistant_message=Message(role="assistant"),
        ):
            responses.append(r)
        assert len(responses) == 1
        assert responses[0].content == "stream success"

    @pytest.mark.asyncio
    async def test_stream_exhausts_retries_and_raises(self):
        @dataclass
        class _AlwaysFailStreamModel(Model):
            id: str = "always-fail-stream"

            async def ainvoke(self, *args, **kwargs) -> ModelResponse:
                return ModelResponse()

            async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
                raise ModelProviderError("always stream fail", model_name="always-fail-stream")
                yield  # make it a generator

            def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
                return ModelResponse()

            def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
                return ModelResponse()

        m = _AlwaysFailStreamModel(retries=1, delay_between_retries=0)
        with pytest.raises(ModelProviderError):
            async for _ in m._ainvoke_stream_with_retry(
                messages=[Message(role="user", content="test")],
                assistant_message=Message(role="assistant"),
            ):
                pass


# ---------------------------------------------------------------------------
# Model._populate_assistant_message() tests
# ---------------------------------------------------------------------------

class TestPopulateAssistantMessage:
    def test_content_set_on_assistant_message(self):
        m = _ConcreteModel()
        assistant_msg = Message(role="assistant")
        provider_response = ModelResponse(role="assistant", content="Hello!")
        m._populate_assistant_message(
            assistant_message=assistant_msg,
            provider_response=provider_response,
        )
        assert assistant_msg.content == "Hello!"

    def test_tool_calls_set_on_assistant_message(self):
        m = _ConcreteModel()
        assistant_msg = Message(role="assistant")
        tool_calls = [{"id": "tc_1", "type": "function", "function": {"name": "search"}}]
        provider_response = ModelResponse(role="assistant", tool_calls=tool_calls)
        m._populate_assistant_message(
            assistant_message=assistant_msg,
            provider_response=provider_response,
        )
        assert assistant_msg.tool_calls is not None
        assert len(assistant_msg.tool_calls) == 1

    def test_reasoning_content_set(self):
        m = _ConcreteModel()
        assistant_msg = Message(role="assistant")
        provider_response = ModelResponse(
            role="assistant",
            content="answer",
            reasoning_content="my reasoning",
        )
        m._populate_assistant_message(
            assistant_message=assistant_msg,
            provider_response=provider_response,
        )
        assert assistant_msg.reasoning_content == "my reasoning"

    def test_metrics_set(self):
        m = _ConcreteModel()
        assistant_msg = Message(role="assistant")
        metrics = Metrics(input_tokens=10, output_tokens=20)
        provider_response = ModelResponse(
            role="assistant",
            content="hi",
            response_usage=metrics,
        )
        m._populate_assistant_message(
            assistant_message=assistant_msg,
            provider_response=provider_response,
        )
        assert assistant_msg.metrics is not None


# ---------------------------------------------------------------------------
# Model.aresponse() basic path (no tool calls)
# ---------------------------------------------------------------------------

class TestModelAResponse:
    @pytest.mark.asyncio
    async def test_aresponse_returns_model_response(self):
        m = _ConcreteModel()
        msgs = [Message(role="user", content="hi")]
        result = await m.aresponse(messages=msgs)
        assert isinstance(result, ModelResponse)

    @pytest.mark.asyncio
    async def test_aresponse_content_from_ainvoke(self):
        m = _ConcreteModel()
        msgs = [Message(role="user", content="hi")]
        result = await m.aresponse(messages=msgs)
        # _ConcreteModel.ainvoke returns ModelResponse(content="ok")
        assert result.content == "ok"
