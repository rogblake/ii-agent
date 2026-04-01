"""Unit tests for ResponseHandler."""

from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

pytest.skip("ii_agent.agents.runs.response_handler was removed during refactoring", allow_module_level=True)

from ii_agent.agents.runs.response_handler import ResponseHandler
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.models.response import ModelResponse, ModelResponseEvent
from ii_agent.agents.runs.agent import RunOutput
from ii_agent.agents.runs.messages import RunMessages
from ii_agent.agents.models.message import Message


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def make_model(assistant_role="assistant", tool_role="tool") -> MagicMock:
    model = MagicMock()
    model.assistant_message_role = assistant_role
    model.tool_message_role = tool_role
    return model


def make_handler(model=None) -> ResponseHandler:
    return ResponseHandler(model=model or make_model())


def make_run_output(run_id: Optional[str] = None) -> RunOutput:
    return RunOutput(
        run_id=run_id or str(uuid4()),
        session_id="session-001",
        user_id="user-001",
        model="gpt-4o",
        agent_name="test-agent",
    )


def make_run_messages(messages=None) -> RunMessages:
    rm = RunMessages()
    if messages:
        rm.messages = messages
    return rm


def make_message(role: str, from_history: bool = False, metrics=None) -> Message:
    msg = Message(role=role, content="test")
    msg.from_history = from_history
    msg.add_to_agent_memory = True
    if metrics:
        msg.metrics = metrics
    return msg


# ---------------------------------------------------------------------------
# ResponseHandler.__init__ tests
# ---------------------------------------------------------------------------


class TestResponseHandlerInit:
    def test_init_sets_model(self):
        model = make_model()
        handler = ResponseHandler(model=model)
        assert handler._model is model


# ---------------------------------------------------------------------------
# update_run_response tests
# ---------------------------------------------------------------------------


class TestUpdateRunResponse:
    def test_sets_content_from_model_response(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="Hello, world!")

        handler.update_run_response(model_response, run_output, run_messages)
        assert run_output.content == "Hello, world!"

    def test_sets_parsed_content_when_output_schema_provided(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="raw text")
        model_response.parsed = {"key": "value"}

        run_context = MagicMock()
        run_context.output_schema = MagicMock()
        run_context.output_schema.__name__ = "MySchema"

        handler.update_run_response(model_response, run_output, run_messages, run_context)
        assert run_output.content == {"key": "value"}
        assert run_output.content_type == "MySchema"

    def test_sets_reasoning_content(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        model_response.reasoning_content = "I reasoned..."

        handler.update_run_response(model_response, run_output, run_messages)
        assert run_output.reasoning_content == "I reasoned..."

    def test_appends_redacted_reasoning_to_existing(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        model_response.reasoning_content = "First"
        model_response.redacted_reasoning_content = " + redacted"

        handler.update_run_response(model_response, run_output, run_messages)
        assert "First" in run_output.reasoning_content
        assert "redacted" in run_output.reasoning_content

    def test_sets_redacted_reasoning_when_no_prior_reasoning(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        model_response.reasoning_content = None
        model_response.redacted_reasoning_content = "redacted only"

        handler.update_run_response(model_response, run_output, run_messages)
        assert run_output.reasoning_content == "redacted only"

    def test_sets_citations(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        model_response.citations = [{"url": "http://example.com"}]

        handler.update_run_response(model_response, run_output, run_messages)
        assert run_output.citations == [{"url": "http://example.com"}]

    def test_sets_provider_data(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        model_response.provider_data = {"usage": {"tokens": 100}}

        handler.update_run_response(model_response, run_output, run_messages)
        assert run_output.model_provider_data == {"usage": {"tokens": 100}}

    def test_sets_tool_executions(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        tool_exec = MagicMock()
        model_response.tool_executions = [tool_exec]

        handler.update_run_response(model_response, run_output, run_messages)
        assert run_output.tools == [tool_exec]

    def test_extends_existing_tool_executions(self):
        handler = make_handler()
        run_output = make_run_output()
        existing_tool = MagicMock()
        run_output.tools = [existing_tool]
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        new_tool = MagicMock()
        model_response.tool_executions = [new_tool]

        handler.update_run_response(model_response, run_output, run_messages)
        assert len(run_output.tools) == 2


# ---------------------------------------------------------------------------
# finalize_run_response tests
# ---------------------------------------------------------------------------


class TestFinalizeRunResponse:
    def test_sets_messages_filtered_by_criteria(self):
        handler = make_handler()
        run_output = make_run_output()

        msg1 = make_message("assistant", from_history=False)
        msg2 = make_message("assistant", from_history=True)  # Should be excluded
        msg3 = make_message("user", from_history=False)
        msg3.add_to_agent_memory = False  # Should be excluded

        run_messages = make_run_messages([msg1, msg2, msg3])
        handler.finalize_run_response(run_output, run_messages)
        assert msg1 in run_output.messages
        assert msg2 not in run_output.messages
        assert msg3 not in run_output.messages

    def test_sets_audio_from_model_response(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        audio = MagicMock()
        model_response.audio = audio

        handler.finalize_run_response(run_output, run_messages, model_response)
        assert run_output.response_audio is audio

    def test_no_audio_does_not_set_response_audio(self):
        handler = make_handler()
        run_output = make_run_output()
        run_messages = make_run_messages()
        model_response = ModelResponse(content="text")
        model_response.audio = None

        handler.finalize_run_response(run_output, run_messages, model_response)
        assert run_output.response_audio is None


# ---------------------------------------------------------------------------
# calculate_run_metrics tests
# ---------------------------------------------------------------------------


class TestCalculateRunMetrics:
    def test_empty_messages_returns_empty_metrics(self):
        handler = make_handler()
        result = handler.calculate_run_metrics([])
        assert isinstance(result, Metrics)

    def test_uses_existing_metrics_if_provided(self):
        handler = make_handler()
        existing = Metrics()
        result = handler.calculate_run_metrics([], current_run_metrics=existing)
        assert result is existing

    def test_sums_metrics_from_assistant_messages(self):
        handler = make_handler()
        metrics = Metrics()
        metrics.input_tokens = 10
        metrics.output_tokens = 20

        msg = make_message("assistant", from_history=False, metrics=metrics)
        result = handler.calculate_run_metrics([msg])
        assert result.input_tokens >= 10

    def test_skips_history_messages(self):
        handler = make_handler()
        metrics = Metrics()
        metrics.input_tokens = 999
        msg = make_message("assistant", from_history=True, metrics=metrics)
        result = handler.calculate_run_metrics([msg])
        # History messages should not be counted
        assert result.input_tokens == 0

    def test_skips_non_assistant_messages(self):
        handler = make_handler()
        metrics = Metrics()
        metrics.input_tokens = 999
        msg = make_message("user", from_history=False, metrics=metrics)
        result = handler.calculate_run_metrics([msg])
        assert result.input_tokens == 0

    def test_preserves_timer_from_current_metrics(self):
        handler = make_handler()
        existing = Metrics()
        existing.timer = MagicMock()
        existing.duration = 5.0
        existing.time_to_first_token = 1.0

        result = handler.calculate_run_metrics([], current_run_metrics=existing)
        assert result.timer is existing.timer
        assert result.duration == 5.0
        assert result.time_to_first_token == 1.0


# ---------------------------------------------------------------------------
# add_fake_tool_results_for_pending_calls tests
# ---------------------------------------------------------------------------


class TestAddFakeToolResultsForPendingCalls:
    def test_adds_fake_result_for_pending_tool_call(self):
        model = make_model()
        handler = ResponseHandler(model=model)

        tool_call_id = str(uuid4())
        assistant_msg = Message(role="assistant", content=None)
        assistant_msg.tool_calls = [
            {"id": tool_call_id, "function": {"name": "my_tool", "arguments": "{}"}}
        ]
        assistant_msg.add_to_agent_memory = True
        assistant_msg.from_history = False

        run_messages = make_run_messages([assistant_msg])
        handler.add_fake_tool_results_for_pending_calls(run_messages, "Tool was cancelled")

        # Should have added a fake tool result message
        tool_messages = [m for m in run_messages.messages if m.role == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0].content == "Tool was cancelled"
        assert tool_messages[0].tool_call_id == tool_call_id

    def test_skips_already_resolved_tool_calls(self):
        model = make_model()
        handler = ResponseHandler(model=model)

        tool_call_id = str(uuid4())
        assistant_msg = Message(role="assistant", content=None)
        assistant_msg.tool_calls = [
            {"id": tool_call_id, "function": {"name": "my_tool", "arguments": "{}"}}
        ]
        assistant_msg.add_to_agent_memory = True
        assistant_msg.from_history = False

        # Pre-existing tool result for this call
        tool_msg = Message(role="tool", content="Already done")
        tool_msg.tool_call_id = tool_call_id
        tool_msg.add_to_agent_memory = True
        tool_msg.from_history = False

        run_messages = make_run_messages([assistant_msg, tool_msg])
        handler.add_fake_tool_results_for_pending_calls(run_messages, "Cancelled")

        # Only the existing tool message should be there, no duplicates
        tool_messages = [m for m in run_messages.messages if m.role == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0].content == "Already done"

    def test_handles_invalid_json_arguments_gracefully(self):
        model = make_model()
        handler = ResponseHandler(model=model)

        tool_call_id = str(uuid4())
        assistant_msg = Message(role="assistant", content=None)
        assistant_msg.tool_calls = [
            {"id": tool_call_id, "function": {"name": "my_tool", "arguments": "not-valid-json"}}
        ]
        assistant_msg.add_to_agent_memory = True
        assistant_msg.from_history = False

        run_messages = make_run_messages([assistant_msg])
        # Should not raise
        handler.add_fake_tool_results_for_pending_calls(
            run_messages, "Error occurred", is_error=True
        )

        tool_messages = [m for m in run_messages.messages if m.role == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0].tool_call_error is True

    def test_handles_missing_tool_call_id(self):
        model = make_model()
        handler = ResponseHandler(model=model)

        assistant_msg = Message(role="assistant", content=None)
        assistant_msg.tool_calls = [
            {"function": {"name": "my_tool", "arguments": "{}"}}  # No "id" key
        ]
        assistant_msg.add_to_agent_memory = True
        assistant_msg.from_history = False

        run_messages = make_run_messages([assistant_msg])
        handler.add_fake_tool_results_for_pending_calls(run_messages, "Error")

        # No fake result should be added (no tool_call_id)
        tool_messages = [m for m in run_messages.messages if m.role == "tool"]
        assert len(tool_messages) == 0

    def test_no_assistant_messages_does_nothing(self):
        model = make_model()
        handler = ResponseHandler(model=model)

        user_msg = make_message("user")
        run_messages = make_run_messages([user_msg])
        handler.add_fake_tool_results_for_pending_calls(run_messages, "Error")

        assert len(run_messages.messages) == 1
