"""Unit tests for ii_agent/engine/runtime/run/agent.py.

Tests cover:
- RunInput dataclass: creation, contains_media(), input_content_string()
- RunOutput dataclass: creation with defaults, status tracking, properties
- RunEvent enum values
- Various event dataclass creation and field defaults
- RUN_EVENT_TYPE_REGISTRY completeness
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# RunInput
# ---------------------------------------------------------------------------

class TestRunInput:
    """Tests for the RunInput dataclass."""

    def test_create_with_string_input(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="Hello agent")
        assert ri.input_content == "Hello agent"

    def test_images_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="hi")
        assert ri.images is None

    def test_videos_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="hi")
        assert ri.videos is None

    def test_audios_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="hi")
        assert ri.audios is None

    def test_files_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="hi")
        assert ri.files is None

    def test_contains_media_false_when_no_media(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="text only")
        assert ri.contains_media() is False

    def test_contains_media_false_with_empty_lists(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="text", images=[], videos=[], audios=[], files=[])
        assert ri.contains_media() is False

    def test_contains_media_true_when_images_present(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        fake_image = MagicMock()
        ri = RunInput(input_content="with image", images=[fake_image])
        assert ri.contains_media() is True

    def test_contains_media_true_when_videos_present(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        fake_video = MagicMock()
        ri = RunInput(input_content="with video", videos=[fake_video])
        assert ri.contains_media() is True

    def test_contains_media_true_when_audios_present(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        fake_audio = MagicMock()
        ri = RunInput(input_content="with audio", audios=[fake_audio])
        assert ri.contains_media() is True

    def test_contains_media_true_when_files_present(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        fake_file = MagicMock()
        ri = RunInput(input_content="with file", files=[fake_file])
        assert ri.contains_media() is True

    def test_input_content_string_returns_str_for_string_input(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="plain text")
        assert ri.input_content_string() == "plain text"

    def test_input_content_string_returns_json_for_pydantic_model(self):
        from pydantic import BaseModel
        from ii_agent.engine.runtime.run.agent import RunInput

        class MySchema(BaseModel):
            field: str = "value"

        model_instance = MySchema()
        ri = RunInput(input_content=model_instance)
        result = ri.input_content_string()
        assert "value" in result

    def test_input_content_string_returns_str_for_dict(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content={"key": "val"})
        result = ri.input_content_string()
        assert isinstance(result, str)

    def test_input_content_string_returns_str_for_list_of_dicts(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content=[{"type": "text", "text": "hello"}])
        result = ri.input_content_string()
        assert isinstance(result, str)

    def test_to_dict_contains_input_content_key(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="query")
        d = ri.to_dict()
        assert "input_content" in d

    def test_to_dict_does_not_contain_images_when_none(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput(input_content="query")
        d = ri.to_dict()
        assert "images" not in d

    def test_from_dict_with_string_input_content(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput.from_dict({"input_content": "reconstructed"})
        assert ri.input_content == "reconstructed"

    def test_from_dict_empty_returns_defaults(self):
        from ii_agent.engine.runtime.run.agent import RunInput

        ri = RunInput.from_dict({})
        assert ri.input_content == ""
        assert ri.images is None


# ---------------------------------------------------------------------------
# RunEvent enum
# ---------------------------------------------------------------------------

class TestRunEvent:
    """Tests for the RunEvent string enum."""

    def test_run_started_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.run_started.value == "RunStarted"

    def test_run_completed_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.run_completed.value == "RunCompleted"

    def test_run_error_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.run_error.value == "RunError"

    def test_run_cancelled_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.run_cancelled.value == "RunCancelled"

    def test_tool_call_started_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.tool_call_started.value == "ToolCallStarted"

    def test_tool_call_completed_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.tool_call_completed.value == "ToolCallCompleted"

    def test_reasoning_started_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.reasoning_started.value == "ReasoningStarted"

    def test_reasoning_delta_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.reasoning_delta.value == "ReasoningDelta"

    def test_reasoning_completed_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.reasoning_completed.value == "ReasoningCompleted"

    def test_sandbox_initialized_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.sandbox_initialized.value == "SandboxInitialized"

    def test_session_summary_started_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.session_summary_started.value == "SessionSummaryStarted"

    def test_session_summary_completed_value(self):
        from ii_agent.engine.runtime.run.agent import RunEvent

        assert RunEvent.session_summary_completed.value == "SessionSummaryCompleted"


# ---------------------------------------------------------------------------
# Event dataclasses creation
# ---------------------------------------------------------------------------

class TestRunStartedEvent:
    def test_default_event_field(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A")
        assert ev.event == "RunStarted"

    def test_run_id_can_be_set(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", run_id="run-1")
        assert ev.run_id == "run-1"

    def test_model_and_provider_can_be_set(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", model="gpt-4", model_provider="openai")
        assert ev.model == "gpt-4"
        assert ev.model_provider == "openai"

    def test_created_at_is_set(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A")
        assert isinstance(ev.created_at, int)
        assert ev.created_at > 0


class TestRunCompletedEvent:
    def test_default_event_field(self):
        from ii_agent.engine.runtime.run.agent import RunCompletedEvent

        ev = RunCompletedEvent(agent_id="a1", agent_name="A")
        assert ev.event == "RunCompleted"

    def test_content_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunCompletedEvent

        ev = RunCompletedEvent(agent_id="a1", agent_name="A")
        assert ev.content is None

    def test_status_can_be_set(self):
        from ii_agent.engine.runtime.run.agent import RunCompletedEvent
        from ii_agent.engine.runtime.run.base import RunStatus

        ev = RunCompletedEvent(agent_id="a1", agent_name="A", status=RunStatus.COMPLETED)
        assert ev.status == RunStatus.COMPLETED

    def test_metrics_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunCompletedEvent

        ev = RunCompletedEvent(agent_id="a1", agent_name="A")
        assert ev.metrics is None


class TestRunErrorEvent:
    def test_default_event_field(self):
        from ii_agent.engine.runtime.run.agent import RunErrorEvent

        ev = RunErrorEvent(agent_id="a1", agent_name="A")
        assert ev.event == "RunError"

    def test_error_fields_default_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunErrorEvent

        ev = RunErrorEvent(agent_id="a1", agent_name="A")
        assert ev.error_type is None
        assert ev.error_id is None
        assert ev.additional_data is None

    def test_error_type_can_be_set(self):
        from ii_agent.engine.runtime.run.agent import RunErrorEvent

        ev = RunErrorEvent(agent_id="a1", agent_name="A", error_type="ValueError")
        assert ev.error_type == "ValueError"


class TestRunCancelledEvent:
    def test_default_event_field(self):
        from ii_agent.engine.runtime.run.agent import RunCancelledEvent

        ev = RunCancelledEvent(agent_id="a1", agent_name="A")
        assert ev.event == "RunCancelled"

    def test_is_cancelled_property(self):
        from ii_agent.engine.runtime.run.agent import RunCancelledEvent

        ev = RunCancelledEvent(agent_id="a1", agent_name="A")
        assert ev.is_cancelled is True

    def test_reason_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunCancelledEvent

        ev = RunCancelledEvent(agent_id="a1", agent_name="A")
        assert ev.reason is None

    def test_reason_can_be_set(self):
        from ii_agent.engine.runtime.run.agent import RunCancelledEvent

        ev = RunCancelledEvent(agent_id="a1", agent_name="A", reason="timeout")
        assert ev.reason == "timeout"


class TestRunPausedEvent:
    def test_default_event_field(self):
        from ii_agent.engine.runtime.run.agent import RunPausedEvent

        ev = RunPausedEvent(agent_id="a1", agent_name="A")
        assert ev.event == "RunPaused"

    def test_is_paused_property(self):
        from ii_agent.engine.runtime.run.agent import RunPausedEvent

        ev = RunPausedEvent(agent_id="a1", agent_name="A")
        assert ev.is_paused is True

    def test_active_requirements_empty_when_none(self):
        from ii_agent.engine.runtime.run.agent import RunPausedEvent

        ev = RunPausedEvent(agent_id="a1", agent_name="A", requirements=None)
        assert ev.active_requirements == []

    def test_tools_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunPausedEvent

        ev = RunPausedEvent(agent_id="a1", agent_name="A")
        assert ev.tools is None


class TestReasoningDeltaEvent:
    def test_default_event_field(self):
        from ii_agent.engine.runtime.run.agent import ReasoningDeltaEvent

        ev = ReasoningDeltaEvent(agent_id="a1", agent_name="A")
        assert ev.event == "ReasoningDelta"

    def test_is_redacted_defaults_to_false(self):
        from ii_agent.engine.runtime.run.agent import ReasoningDeltaEvent

        ev = ReasoningDeltaEvent(agent_id="a1", agent_name="A")
        assert ev.is_redacted is False

    def test_reasoning_content_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import ReasoningDeltaEvent

        ev = ReasoningDeltaEvent(agent_id="a1", agent_name="A")
        assert ev.reasoning_content is None

    def test_redacted_reasoning_content_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import ReasoningDeltaEvent

        ev = ReasoningDeltaEvent(agent_id="a1", agent_name="A")
        assert ev.redacted_reasoning_content is None


class TestBaseAgentRunEvent:
    """Tests for BaseAgentRunEvent properties."""

    def test_tools_requiring_confirmation_empty_when_no_tools(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", tools=None)
        assert ev.tools_requiring_confirmation == []

    def test_tools_requiring_user_input_empty_when_no_tools(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", tools=None)
        assert ev.tools_requiring_user_input == []

    def test_tools_awaiting_external_execution_empty_when_no_tools(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", tools=None)
        assert ev.tools_awaiting_external_execution == []

    def test_delegated_from_defaults_to_none(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A")
        assert ev.delegated_from is None

    def test_is_sub_agent_event_defaults_to_false(self):
        from ii_agent.engine.runtime.run.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A")
        assert ev.is_sub_agent_event is False


# ---------------------------------------------------------------------------
# RunOutput
# ---------------------------------------------------------------------------

class TestRunOutput:
    """Tests for the RunOutput dataclass."""

    def _make(self, **kwargs):
        from ii_agent.engine.runtime.run.agent import RunOutput
        from ii_agent.engine.runtime.run.base import RunStatus

        defaults = dict(
            run_id="run-1",
            session_id="sess-1",
            user_id="user-1",
            model="gpt-4o",
            agent_name="TestAgent",
        )
        defaults.update(kwargs)
        return RunOutput(**defaults)

    def test_create_minimal(self):
        output = self._make()
        assert output.run_id == "run-1"
        assert output.session_id == "sess-1"
        assert output.user_id == "user-1"
        assert output.model == "gpt-4o"
        assert output.agent_name == "TestAgent"

    def test_status_defaults_to_running(self):
        from ii_agent.engine.runtime.run.base import RunStatus

        output = self._make()
        assert output.status == RunStatus.RUNNING

    def test_content_defaults_to_none(self):
        output = self._make()
        assert output.content is None

    def test_messages_defaults_to_none(self):
        output = self._make()
        assert output.messages is None

    def test_tools_defaults_to_none(self):
        output = self._make()
        assert output.tools is None

    def test_images_defaults_to_none(self):
        output = self._make()
        assert output.images is None

    def test_videos_defaults_to_none(self):
        output = self._make()
        assert output.videos is None

    def test_audio_defaults_to_none(self):
        output = self._make()
        assert output.audio is None

    def test_files_defaults_to_none(self):
        output = self._make()
        assert output.files is None

    def test_created_at_is_integer(self):
        output = self._make()
        assert isinstance(output.created_at, int)
        assert output.created_at > 0

    def test_is_paused_false_by_default(self):
        output = self._make()
        assert output.is_paused is False

    def test_is_paused_true_when_status_paused(self):
        from ii_agent.engine.runtime.run.base import RunStatus

        output = self._make(status=RunStatus.PAUSED)
        assert output.is_paused is True

    def test_is_cancelled_false_by_default(self):
        output = self._make()
        assert output.is_cancelled is False

    def test_is_cancelled_true_when_status_aborted(self):
        from ii_agent.engine.runtime.run.base import RunStatus

        output = self._make(status=RunStatus.ABORTED)
        assert output.is_cancelled is True

    def test_is_sub_agent_response_false_without_delegation(self):
        output = self._make()
        assert output.is_sub_agent_response is False

    def test_is_sub_agent_response_true_with_delegated_from(self):
        output = self._make(delegated_from="ParentAgent")
        assert output.is_sub_agent_response is True

    def test_is_sub_agent_response_true_with_parent_run_id(self):
        output = self._make(parent_run_id="parent-run-1")
        assert output.is_sub_agent_response is True

    def test_active_requirements_empty_when_none(self):
        output = self._make()
        assert output.active_requirements == []

    def test_tools_requiring_confirmation_empty_when_no_tools(self):
        output = self._make()
        assert output.tools_requiring_confirmation == []

    def test_tools_requiring_user_input_empty_when_no_tools(self):
        output = self._make()
        assert output.tools_requiring_user_input == []

    def test_tools_awaiting_external_execution_empty_when_no_tools(self):
        output = self._make()
        assert output.tools_awaiting_external_execution == []

    def test_add_member_run_appends(self):
        from ii_agent.engine.runtime.run.agent import RunOutput

        parent = self._make()
        child = self._make(run_id="child-run", delegated_from="TestAgent")
        parent.add_member_run(child)
        assert parent.member_responses is not None
        assert len(parent.member_responses) == 1

    def test_add_member_run_aggregates_images(self):
        fake_image = MagicMock()
        parent = self._make()
        child = self._make(run_id="child-run", images=[fake_image])
        parent.add_member_run(child)
        assert parent.images is not None
        assert fake_image in parent.images

    def test_get_content_as_string_for_string_content(self):
        output = self._make(content="hello world")
        assert output.get_content_as_string() == "hello world"

    def test_get_content_as_string_for_none_content(self):
        import json

        output = self._make(content=None)
        result = output.get_content_as_string()
        assert result == json.dumps(None)

    def test_to_dict_contains_required_fields(self):
        output = self._make()
        d = output.to_dict()
        assert "run_id" in d
        assert "session_id" in d
        assert "agent_name" in d

    def test_to_json_returns_valid_json(self):
        import json

        output = self._make(content="test response")
        json_str = output.to_json()
        parsed = json.loads(json_str)
        assert parsed["run_id"] == "run-1"

    def test_from_dict_round_trip_preserves_run_id(self):
        from ii_agent.engine.runtime.run.agent import RunOutput

        output = self._make(content="some content")
        d = output.to_dict()
        recovered = RunOutput.from_dict(d)
        assert recovered.run_id == "run-1"


# ---------------------------------------------------------------------------
# RUN_EVENT_TYPE_REGISTRY
# ---------------------------------------------------------------------------

class TestRunEventTypeRegistry:
    """Tests for the RUN_EVENT_TYPE_REGISTRY mapping completeness."""

    def test_registry_contains_run_started(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, RunStartedEvent

        assert RUN_EVENT_TYPE_REGISTRY["RunStarted"] is RunStartedEvent

    def test_registry_contains_run_completed(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, RunCompletedEvent

        assert RUN_EVENT_TYPE_REGISTRY["RunCompleted"] is RunCompletedEvent

    def test_registry_contains_run_error(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, RunErrorEvent

        assert RUN_EVENT_TYPE_REGISTRY["RunError"] is RunErrorEvent

    def test_registry_contains_run_cancelled(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, RunCancelledEvent

        assert RUN_EVENT_TYPE_REGISTRY["RunCancelled"] is RunCancelledEvent

    def test_registry_contains_tool_call_started(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, ToolCallStartedEvent

        assert RUN_EVENT_TYPE_REGISTRY["ToolCallStarted"] is ToolCallStartedEvent

    def test_registry_contains_tool_call_completed(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, ToolCallCompletedEvent

        assert RUN_EVENT_TYPE_REGISTRY["ToolCallCompleted"] is ToolCallCompletedEvent

    def test_registry_contains_reasoning_started(self):
        from ii_agent.engine.runtime.run.agent import RUN_EVENT_TYPE_REGISTRY, ReasoningStartedEvent

        assert RUN_EVENT_TYPE_REGISTRY["ReasoningStarted"] is ReasoningStartedEvent

    def test_run_output_event_from_dict_raises_for_unknown_type(self):
        from ii_agent.engine.runtime.run.agent import run_output_event_from_dict

        with pytest.raises(ValueError, match="Unknown event type"):
            run_output_event_from_dict({"event": "NonExistentEvent"})

    def test_run_output_event_from_dict_creates_run_started(self):
        from ii_agent.engine.runtime.run.agent import run_output_event_from_dict, RunStartedEvent

        data = {
            "event": "RunStarted",
            "agent_id": "a1",
            "agent_name": "TestAgent",
        }
        ev = run_output_event_from_dict(data)
        assert isinstance(ev, RunStartedEvent)
