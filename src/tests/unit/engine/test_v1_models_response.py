"""Unit tests for ii_agent/agent/runtime/models/response.py.

Tests cover:
- ToolExecution dataclass: creation, field defaults, is_paused, to_dict(), from_dict()
- ModelResponseEvent enum
- ModelResponse dataclass: creation, field defaults, to_dict() / from_dict()
- FileType enum
"""

from __future__ import annotations

import pytest
from time import time


# ---------------------------------------------------------------------------
# ModelResponseEvent enum
# ---------------------------------------------------------------------------


class TestModelResponseEvent:
    """Tests for the ModelResponseEvent string enum."""

    def test_tool_call_paused_value(self):
        from ii_agent.agents.models.response import ModelResponseEvent

        assert ModelResponseEvent.tool_call_paused.value == "ToolCallPaused"

    def test_tool_call_started_value(self):
        from ii_agent.agents.models.response import ModelResponseEvent

        assert ModelResponseEvent.tool_call_started.value == "ToolCallStarted"

    def test_tool_call_completed_value(self):
        from ii_agent.agents.models.response import ModelResponseEvent

        assert ModelResponseEvent.tool_call_completed.value == "ToolCallCompleted"

    def test_assistant_response_value(self):
        from ii_agent.agents.models.response import ModelResponseEvent

        assert ModelResponseEvent.assistant_response.value == "AssistantResponse"


# ---------------------------------------------------------------------------
# FileType enum
# ---------------------------------------------------------------------------


class TestFileType:
    def test_mp4_value(self):
        from ii_agent.agents.models.response import FileType

        assert FileType.MP4.value == "mp4"

    def test_gif_value(self):
        from ii_agent.agents.models.response import FileType

        assert FileType.GIF.value == "gif"

    def test_mp3_value(self):
        from ii_agent.agents.models.response import FileType

        assert FileType.MP3.value == "mp3"

    def test_wav_value(self):
        from ii_agent.agents.models.response import FileType

        assert FileType.WAV.value == "wav"


# ---------------------------------------------------------------------------
# ToolExecution
# ---------------------------------------------------------------------------


class TestToolExecution:
    """Tests for the ToolExecution dataclass."""

    def test_create_empty(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.tool_call_id is None
        assert te.tool_name is None

    def test_create_with_all_fields(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(
            tool_call_id="call-123",
            tool_name="search_web",
            tool_args={"query": "hello"},
            tool_call_error=False,
            result="Found results",
            display_name="Web Search",
            tool_logo="https://example.com/logo.png",
            stop_after_tool_call=False,
            requires_confirmation=False,
            confirmed=None,
            requires_user_input=False,
            external_execution_required=False,
        )
        assert te.tool_call_id == "call-123"
        assert te.tool_name == "search_web"
        assert te.tool_args == {"query": "hello"}
        assert te.result == "Found results"
        assert te.display_name == "Web Search"

    def test_tool_call_id_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.tool_call_id is None

    def test_tool_name_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.tool_name is None

    def test_tool_args_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.tool_args is None

    def test_tool_call_error_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.tool_call_error is None

    def test_result_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.result is None

    def test_display_name_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.display_name is None

    def test_tool_logo_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.tool_logo is None

    def test_stop_after_tool_call_defaults_to_false(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.stop_after_tool_call is False

    def test_created_at_is_integer(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert isinstance(te.created_at, int)
        assert te.created_at > 0

    def test_requires_confirmation_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.requires_confirmation is None

    def test_confirmed_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.confirmed is None

    def test_requires_user_input_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.requires_user_input is None

    def test_user_input_schema_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.user_input_schema is None

    def test_external_execution_required_defaults_to_none(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.external_execution_required is None

    def test_is_paused_false_when_no_requirements(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution()
        assert te.is_paused is False

    def test_is_paused_true_when_requires_confirmation(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(requires_confirmation=True)
        assert te.is_paused is True

    def test_is_paused_true_when_requires_user_input(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(requires_user_input=True)
        assert te.is_paused is True

    def test_is_paused_true_when_external_execution_required(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(external_execution_required=True)
        assert te.is_paused is True

    def test_to_dict_returns_dict(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(tool_call_id="c1", tool_name="my_tool")
        result = te.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_tool_call_id(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(tool_call_id="call-abc")
        result = te.to_dict()
        assert result["tool_call_id"] == "call-abc"

    def test_to_dict_contains_tool_name(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(tool_name="execute_code")
        result = te.to_dict()
        assert result["tool_name"] == "execute_code"

    def test_to_dict_contains_tool_args(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(tool_args={"cmd": "ls"})
        result = te.to_dict()
        assert result["tool_args"] == {"cmd": "ls"}

    def test_to_dict_result_is_included(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution(result="output text")
        result = te.to_dict()
        assert result["result"] == "output text"

    def test_to_dict_with_metrics(self):
        from ii_agent.agents.models.response import ToolExecution
        from ii_agent.agents.models.metrics import Metrics

        m = Metrics(input_tokens=10, output_tokens=20, total_tokens=30)
        te = ToolExecution(metrics=m)
        result = te.to_dict()
        assert "metrics" in result

    def test_from_dict_creates_instance_with_tool_name(self):
        from ii_agent.agents.models.response import ToolExecution

        data = {"tool_name": "run_code", "tool_call_id": "id-1"}
        te = ToolExecution.from_dict(data)
        assert te.tool_name == "run_code"
        assert te.tool_call_id == "id-1"

    def test_from_dict_empty_dict(self):
        from ii_agent.agents.models.response import ToolExecution

        te = ToolExecution.from_dict({})
        assert te.tool_name is None
        assert te.tool_call_id is None

    def test_from_dict_preserves_stop_after_tool_call(self):
        from ii_agent.agents.models.response import ToolExecution

        data = {"stop_after_tool_call": True}
        te = ToolExecution.from_dict(data)
        assert te.stop_after_tool_call is True

    def test_from_dict_with_user_input_schema(self):
        from ii_agent.agents.models.response import ToolExecution

        data = {
            "user_input_schema": [
                {"name": "email", "field_type": "str", "description": None, "value": None}
            ]
        }
        te = ToolExecution.from_dict(data)
        assert te.user_input_schema is not None
        assert len(te.user_input_schema) == 1
        assert te.user_input_schema[0].name == "email"

    def test_roundtrip_to_dict_from_dict(self):
        from ii_agent.agents.models.response import ToolExecution

        original = ToolExecution(
            tool_call_id="c-1",
            tool_name="web_search",
            tool_args={"q": "python"},
            result="Found results",
        )
        recovered = ToolExecution.from_dict(original.to_dict())
        assert recovered.tool_call_id == original.tool_call_id
        assert recovered.tool_name == original.tool_name
        assert recovered.tool_args == original.tool_args

    def test_to_dict_with_tool_result_pydantic_model(self):
        from pydantic import BaseModel
        from ii_agent.agents.models.response import ToolExecution

        class FakeToolResult(BaseModel):
            value: str = "ok"

        te = ToolExecution(result=FakeToolResult())
        d = te.to_dict()
        # Pydantic model result should be serialized as a dict
        assert isinstance(d["result"], dict)


# ---------------------------------------------------------------------------
# ModelResponse
# ---------------------------------------------------------------------------


class TestModelResponse:
    """Tests for the ModelResponse dataclass."""

    def test_create_empty(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.role is None
        assert mr.content is None

    def test_event_defaults_to_assistant_response(self):
        from ii_agent.agents.models.response import ModelResponse, ModelResponseEvent

        mr = ModelResponse()
        assert mr.event == ModelResponseEvent.assistant_response.value

    def test_tool_calls_defaults_to_empty_list(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.tool_calls == []

    def test_tool_executions_defaults_to_empty_list(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.tool_executions == []

    def test_is_delta_defaults_to_false(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.is_delta is False

    def test_reasoning_content_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.reasoning_content is None

    def test_redacted_reasoning_content_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.redacted_reasoning_content is None

    def test_citations_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.citations is None

    def test_response_usage_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.response_usage is None

    def test_provider_data_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.provider_data is None

    def test_extra_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.extra is None

    def test_updated_session_state_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.updated_session_state is None

    def test_delta_status_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.delta_status is None

    def test_images_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.images is None

    def test_videos_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.videos is None

    def test_audios_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.audios is None

    def test_files_defaults_to_none(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse()
        assert mr.files is None

    def test_create_with_role_and_content(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse(role="assistant", content="Hello!")
        assert mr.role == "assistant"
        assert mr.content == "Hello!"

    def test_create_with_tool_calls(self):
        from ii_agent.agents.models.response import ModelResponse

        tool_calls = [{"id": "c1", "function": {"name": "search"}}]
        mr = ModelResponse(tool_calls=tool_calls)
        assert len(mr.tool_calls) == 1

    def test_to_dict_returns_dict(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse(role="assistant", content="Hi")
        result = mr.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_preserves_event_field(self):
        from ii_agent.agents.models.response import ModelResponse, ModelResponseEvent

        mr = ModelResponse()
        result = mr.to_dict()
        assert result["event"] == ModelResponseEvent.assistant_response.value

    def test_to_dict_with_tool_executions(self):
        from ii_agent.agents.models.response import ModelResponse, ToolExecution

        te = ToolExecution(tool_call_id="c1", tool_name="tool_a")
        mr = ModelResponse(tool_executions=[te])
        result = mr.to_dict()
        assert "tool_executions" in result
        assert len(result["tool_executions"]) == 1

    def test_from_dict_round_trip_preserves_content(self):
        from ii_agent.agents.models.response import ModelResponse

        mr = ModelResponse(role="assistant", content="response text")
        d = mr.to_dict()
        recovered = ModelResponse.from_dict(d)
        assert recovered.content == "response text"
        assert recovered.role == "assistant"

    def test_from_dict_with_tool_executions(self):
        from ii_agent.agents.models.response import ModelResponse

        data = {
            "tool_executions": [{"tool_call_id": "c1", "tool_name": "do_something"}],
            "event": "AssistantResponse",
        }
        mr = ModelResponse.from_dict(data)
        assert mr.tool_executions is not None
        assert len(mr.tool_executions) == 1
        assert mr.tool_executions[0].tool_name == "do_something"
