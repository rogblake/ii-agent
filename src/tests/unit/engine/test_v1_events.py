"""Unit tests for ii_agent.agent.runtime.run.events module.

Tests cover all create_*_event() factory functions and handle_event().
Each factory maps fields from a RunOutput to a specific event dataclass.
"""
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.runtime.models.message import Citations, Message, MessageReferences, UrlCitation
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.models.response import ToolExecution
from ii_agent.agent.runtime.run.agent import (
    MemoryUpdateCompletedEvent,
    MemoryUpdateStartedEvent,
    PostHookCompletedEvent,
    PostHookStartedEvent,
    PreHookCompletedEvent,
    PreHookStartedEvent,
    ReasoningCompletedEvent,
    ReasoningDeltaEvent,
    ReasoningStartedEvent,
    RunCancelledEvent,
    RunCompletedEvent,
    RunContentCompletedEvent,
    RunContentDeltaEvent,
    RunContentEvent,
    RunErrorEvent,
    RunEvent,
    RunInput,
    RunOutput,
    RunPausedEvent,
    RunStartedEvent,
    AgentSummaryCompletedEvent,
    AgentSummaryStartedEvent,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from ii_agent.agent.runtime.run.base import RunStatus
from ii_agent.agent.runtime.run.events import (
    create_memory_update_completed_event,
    create_memory_update_started_event,
    create_post_hook_completed_event,
    create_post_hook_started_event,
    create_pre_hook_completed_event,
    create_pre_hook_started_event,
    create_reasoning_completed_event,
    create_reasoning_delta_event,
    create_reasoning_started_event,
    create_run_cancelled_event,
    create_run_completed_event,
    create_run_content_completed_event,
    create_run_content_delta_event,
    create_run_error_event,
    create_run_output_content_event,
    create_run_paused_event,
    create_run_started_event,
    create_tool_call_completed_event,
    create_tool_call_started_event,
    handle_event,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_run_output():
    """Return a fully-populated RunOutput for use in event factory tests."""
    return RunOutput(
        run_id="run-001",
        session_id="session-abc",
        user_id="user-xyz",
        model="gpt-4o",
        agent_name="TestAgent",
        agent_id="agent-001",
        model_provider="OpenAI",
        content="Hello, I am the agent.",
        content_type="str",
        reasoning_content="I reasoned about this.",
        status=RunStatus.COMPLETED,
        metrics=Metrics(input_tokens=100, output_tokens=50),
    )


@pytest.fixture
def minimal_run_output():
    """Return a minimal RunOutput with only required fields."""
    return RunOutput(
        run_id="run-min",
        session_id="session-min",
        user_id="user-min",
        model="claude-3",
        agent_name="MinAgent",
    )


@pytest.fixture
def tool_execution():
    """Return a basic ToolExecution object."""
    return ToolExecution(
        tool_call_id="tool-call-001",
        tool_name="search_tool",
        tool_args={"query": "test search"},
        result="Search results here",
    )


@pytest.fixture
def run_input():
    """Return a basic RunInput object."""
    return RunInput(input_content="What is the weather?")


@pytest.fixture
def citations_obj():
    """Return a Citations object."""
    return Citations(
        urls=[UrlCitation(url="https://example.com", title="Example")],
    )


# ---------------------------------------------------------------------------
# create_run_started_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunStartedEvent:
    def test_returns_run_started_event(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert isinstance(event, RunStartedEvent)

    def test_event_type_is_run_started(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.event == RunEvent.run_started.value

    def test_session_id_copied(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_agent_id_copied(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.agent_id == "agent-001"

    def test_agent_name_copied(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.agent_name == "TestAgent"

    def test_run_id_copied(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.run_id == "run-001"

    def test_model_copied(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.model == "gpt-4o"

    def test_model_provider_copied(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        assert event.model_provider == "OpenAI"

    def test_with_minimal_run_output(self, minimal_run_output):
        event = create_run_started_event(minimal_run_output)
        assert isinstance(event, RunStartedEvent)
        assert event.session_id == "session-min"
        assert event.run_id == "run-min"


# ---------------------------------------------------------------------------
# create_run_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunCompletedEvent:
    def test_returns_run_completed_event(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert isinstance(event, RunCompletedEvent)

    def test_event_type_is_run_completed(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.event == RunEvent.run_completed.value

    def test_session_id_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.run_id == "run-001"

    def test_content_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.content == "Hello, I am the agent."

    def test_content_type_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.content_type == "str"

    def test_reasoning_content_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.reasoning_content == "I reasoned about this."

    def test_status_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.status == RunStatus.COMPLETED

    def test_metrics_copied(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        assert event.metrics is not None
        assert event.metrics.input_tokens == 100

    def test_citations_none_by_default(self, minimal_run_output):
        event = create_run_completed_event(minimal_run_output)
        assert event.citations is None

    def test_with_citations(self, mock_run_output, citations_obj):
        mock_run_output.citations = citations_obj
        event = create_run_completed_event(mock_run_output)
        assert event.citations is citations_obj


# ---------------------------------------------------------------------------
# create_run_paused_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunPausedEvent:
    def test_returns_run_paused_event(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert isinstance(event, RunPausedEvent)

    def test_event_type_is_run_paused(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert event.event == RunEvent.run_paused.value

    def test_session_id_copied(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_tools_none_by_default(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert event.tools is None

    def test_tools_passed_through(self, mock_run_output, tool_execution):
        event = create_run_paused_event(mock_run_output, tools=[tool_execution])
        assert event.tools == [tool_execution]

    def test_requirements_none_by_default(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert event.requirements is None

    def test_content_copied(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert event.content == "Hello, I am the agent."

    def test_run_id_copied(self, mock_run_output):
        event = create_run_paused_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_run_error_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunErrorEvent:
    def test_returns_run_error_event(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="Something went wrong")
        assert isinstance(event, RunErrorEvent)

    def test_event_type_is_run_error(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="Error msg")
        assert event.event == RunEvent.run_error.value

    def test_error_message_set_as_content(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="Connection timeout")
        assert event.content == "Connection timeout"

    def test_session_id_copied(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="err")
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="err")
        assert event.run_id == "run-001"

    def test_agent_name_copied(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="err")
        assert event.agent_name == "TestAgent"

    def test_model_copied(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="err")
        assert event.model == "gpt-4o"

    def test_empty_error_string(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="")
        assert event.content == ""


# ---------------------------------------------------------------------------
# create_run_cancelled_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunCancelledEvent:
    def test_returns_run_cancelled_event(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="User cancelled")
        assert isinstance(event, RunCancelledEvent)

    def test_event_type_is_run_cancelled(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="cancelled")
        assert event.event == RunEvent.run_cancelled.value

    def test_reason_set(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="User requested cancellation")
        assert event.reason == "User requested cancellation"

    def test_session_id_copied(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="r")
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="r")
        assert event.run_id == "run-001"

    def test_agent_id_copied(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="r")
        assert event.agent_id == "agent-001"

    def test_is_cancelled_property(self, mock_run_output):
        event = create_run_cancelled_event(mock_run_output, reason="r")
        assert event.is_cancelled is True


# ---------------------------------------------------------------------------
# create_pre_hook_started_event() tests
# ---------------------------------------------------------------------------


class TestCreatePreHookStartedEvent:
    def test_returns_pre_hook_started_event(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output)
        assert isinstance(event, PreHookStartedEvent)

    def test_event_type_is_pre_hook_started(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output)
        assert event.event == RunEvent.pre_hook_started.value

    def test_session_id_copied(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_pre_hook_name_none_by_default(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output)
        assert event.pre_hook_name is None

    def test_pre_hook_name_passed_through(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output, pre_hook_name="my_pre_hook")
        assert event.pre_hook_name == "my_pre_hook"

    def test_run_input_none_by_default(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output)
        assert event.run_input is None

    def test_run_input_deep_copied(self, mock_run_output, run_input):
        event = create_pre_hook_started_event(mock_run_output, run_input=run_input)
        assert event.run_input is not None
        # Should be a deep copy, not the same object
        assert event.run_input is not run_input
        assert event.run_input.input_content == run_input.input_content

    def test_run_id_copied(self, mock_run_output):
        event = create_pre_hook_started_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_pre_hook_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreatePreHookCompletedEvent:
    def test_returns_pre_hook_completed_event(self, mock_run_output):
        event = create_pre_hook_completed_event(mock_run_output)
        assert isinstance(event, PreHookCompletedEvent)

    def test_event_type_is_pre_hook_completed(self, mock_run_output):
        event = create_pre_hook_completed_event(mock_run_output)
        assert event.event == RunEvent.pre_hook_completed.value

    def test_pre_hook_name_passed(self, mock_run_output):
        event = create_pre_hook_completed_event(mock_run_output, pre_hook_name="validation_hook")
        assert event.pre_hook_name == "validation_hook"

    def test_run_input_deep_copied(self, mock_run_output, run_input):
        event = create_pre_hook_completed_event(mock_run_output, run_input=run_input)
        assert event.run_input is not run_input
        assert event.run_input.input_content == run_input.input_content

    def test_session_id_copied(self, mock_run_output):
        event = create_pre_hook_completed_event(mock_run_output)
        assert event.session_id == "session-abc"


# ---------------------------------------------------------------------------
# create_post_hook_started_event() tests
# ---------------------------------------------------------------------------


class TestCreatePostHookStartedEvent:
    def test_returns_post_hook_started_event(self, mock_run_output):
        event = create_post_hook_started_event(mock_run_output)
        assert isinstance(event, PostHookStartedEvent)

    def test_event_type_is_post_hook_started(self, mock_run_output):
        event = create_post_hook_started_event(mock_run_output)
        assert event.event == RunEvent.post_hook_started.value

    def test_post_hook_name_none_by_default(self, mock_run_output):
        event = create_post_hook_started_event(mock_run_output)
        assert event.post_hook_name is None

    def test_post_hook_name_passed(self, mock_run_output):
        event = create_post_hook_started_event(mock_run_output, post_hook_name="send_notification")
        assert event.post_hook_name == "send_notification"

    def test_session_id_copied(self, mock_run_output):
        event = create_post_hook_started_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_post_hook_started_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_post_hook_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreatePostHookCompletedEvent:
    def test_returns_post_hook_completed_event(self, mock_run_output):
        event = create_post_hook_completed_event(mock_run_output)
        assert isinstance(event, PostHookCompletedEvent)

    def test_event_type_is_post_hook_completed(self, mock_run_output):
        event = create_post_hook_completed_event(mock_run_output)
        assert event.event == RunEvent.post_hook_completed.value

    def test_post_hook_name_passed(self, mock_run_output):
        event = create_post_hook_completed_event(mock_run_output, post_hook_name="done_hook")
        assert event.post_hook_name == "done_hook"

    def test_session_id_copied(self, mock_run_output):
        event = create_post_hook_completed_event(mock_run_output)
        assert event.session_id == "session-abc"


# ---------------------------------------------------------------------------
# create_memory_update_started_event() tests
# ---------------------------------------------------------------------------


class TestCreateMemoryUpdateStartedEvent:
    def test_returns_memory_update_started_event(self, mock_run_output):
        event = create_memory_update_started_event(mock_run_output)
        assert isinstance(event, MemoryUpdateStartedEvent)

    def test_event_type_is_memory_update_started(self, mock_run_output):
        event = create_memory_update_started_event(mock_run_output)
        assert event.event == RunEvent.memory_update_started.value

    def test_session_id_copied(self, mock_run_output):
        event = create_memory_update_started_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_memory_update_started_event(mock_run_output)
        assert event.run_id == "run-001"

    def test_agent_name_copied(self, mock_run_output):
        event = create_memory_update_started_event(mock_run_output)
        assert event.agent_name == "TestAgent"

    def test_model_copied(self, mock_run_output):
        event = create_memory_update_started_event(mock_run_output)
        assert event.model == "gpt-4o"


# ---------------------------------------------------------------------------
# create_memory_update_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreateMemoryUpdateCompletedEvent:
    def test_returns_memory_update_completed_event(self, mock_run_output):
        event = create_memory_update_completed_event(mock_run_output)
        assert isinstance(event, MemoryUpdateCompletedEvent)

    def test_event_type_is_memory_update_completed(self, mock_run_output):
        event = create_memory_update_completed_event(mock_run_output)
        assert event.event == RunEvent.memory_update_completed.value

    def test_session_id_copied(self, mock_run_output):
        event = create_memory_update_completed_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_memory_update_completed_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_reasoning_started_event() tests
# ---------------------------------------------------------------------------


class TestCreateReasoningStartedEvent:
    def test_returns_reasoning_started_event(self, mock_run_output):
        event = create_reasoning_started_event(mock_run_output)
        assert isinstance(event, ReasoningStartedEvent)

    def test_event_type_is_reasoning_started(self, mock_run_output):
        event = create_reasoning_started_event(mock_run_output)
        assert event.event == RunEvent.reasoning_started.value

    def test_session_id_copied(self, mock_run_output):
        event = create_reasoning_started_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_reasoning_started_event(mock_run_output)
        assert event.run_id == "run-001"

    def test_model_copied(self, mock_run_output):
        event = create_reasoning_started_event(mock_run_output)
        assert event.model == "gpt-4o"


# ---------------------------------------------------------------------------
# create_reasoning_delta_event() tests
# ---------------------------------------------------------------------------


class TestCreateReasoningDeltaEvent:
    def test_returns_reasoning_delta_event(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output)
        assert isinstance(event, ReasoningDeltaEvent)

    def test_event_type_is_reasoning_delta(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output)
        assert event.event == RunEvent.reasoning_delta.value

    def test_session_id_copied(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_reasoning_content_passed(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output, reasoning_content="chunk of thought")
        assert event.reasoning_content == "chunk of thought"

    def test_redacted_reasoning_content_passed(self, mock_run_output):
        event = create_reasoning_delta_event(
            mock_run_output, redacted_reasoning_content="encrypted_chunk"
        )
        assert event.redacted_reasoning_content == "encrypted_chunk"

    def test_is_redacted_default_false(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output)
        assert event.is_redacted is False

    def test_is_redacted_passed_through(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output, is_redacted=True)
        assert event.is_redacted is True

    def test_provider_data_passed(self, mock_run_output):
        event = create_reasoning_delta_event(
            mock_run_output, provider_data={"signature": "sig_abc"}
        )
        assert event.provider_data == {"signature": "sig_abc"}

    def test_none_reasoning_content_by_default(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output)
        assert event.reasoning_content is None

    def test_run_id_copied(self, mock_run_output):
        event = create_reasoning_delta_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_reasoning_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreateReasoningCompletedEvent:
    def test_returns_reasoning_completed_event(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output)
        assert isinstance(event, ReasoningCompletedEvent)

    def test_event_type_is_reasoning_completed(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output)
        assert event.event == RunEvent.reasoning_completed.value

    def test_session_id_copied(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_content_passed(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output, content="Final reasoning summary")
        assert event.content == "Final reasoning summary"

    def test_content_type_defaults_to_str(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output)
        assert event.content_type == "str"

    def test_content_type_passed(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output, content_type="json")
        assert event.content_type == "json"

    def test_provider_data_passed(self, mock_run_output):
        event = create_reasoning_completed_event(
            mock_run_output, provider_data={"encrypted": "data"}
        )
        assert event.provider_data == {"encrypted": "data"}

    def test_run_id_copied(self, mock_run_output):
        event = create_reasoning_completed_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_tool_call_started_event() tests
# ---------------------------------------------------------------------------


class TestCreateToolCallStartedEvent:
    def test_returns_tool_call_started_event(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        assert isinstance(event, ToolCallStartedEvent)

    def test_event_type_is_tool_call_started(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        assert event.event == RunEvent.tool_call_started.value

    def test_tool_passed(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        assert event.tool is tool_execution
        assert event.tool.tool_name == "search_tool"

    def test_session_id_copied(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        assert event.run_id == "run-001"

    def test_agent_name_copied(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        assert event.agent_name == "TestAgent"


# ---------------------------------------------------------------------------
# create_tool_call_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreateToolCallCompletedEvent:
    def test_returns_tool_call_completed_event(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert isinstance(event, ToolCallCompletedEvent)

    def test_event_type_is_tool_call_completed(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.event == RunEvent.tool_call_completed.value

    def test_tool_passed(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.tool is tool_execution

    def test_content_none_by_default(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.content is None

    def test_content_passed(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(
            mock_run_output, tool=tool_execution, content="Tool output"
        )
        assert event.content == "Tool output"

    def test_images_copied_from_run_output(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.images == mock_run_output.images

    def test_videos_copied_from_run_output(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.videos == mock_run_output.videos

    def test_audio_copied_from_run_output(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.audio == mock_run_output.audio

    def test_session_id_copied(self, mock_run_output, tool_execution):
        event = create_tool_call_completed_event(mock_run_output, tool=tool_execution)
        assert event.session_id == "session-abc"


# ---------------------------------------------------------------------------
# create_run_content_delta_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunContentDeltaEvent:
    def test_returns_run_content_delta_event(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output)
        assert isinstance(event, RunContentDeltaEvent)

    def test_event_type_is_run_content_delta(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output)
        assert event.event == RunEvent.run_content_delta.value

    def test_content_none_by_default(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output)
        assert event.content is None

    def test_content_passed(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output, content="delta chunk")
        assert event.content == "delta chunk"

    def test_content_type_defaults_to_str(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output)
        assert event.content_type == "str"

    def test_content_type_passed(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output, content_type="markdown")
        assert event.content_type == "markdown"

    def test_session_id_copied(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# create_run_content_completed_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunContentCompletedEvent:
    def test_returns_run_content_completed_event(self, mock_run_output):
        event = create_run_content_completed_event(mock_run_output)
        assert isinstance(event, RunContentCompletedEvent)

    def test_event_type_is_run_content_completed(self, mock_run_output):
        event = create_run_content_completed_event(mock_run_output)
        assert event.event == RunEvent.run_content_completed.value

    def test_content_copied_from_run_output(self, mock_run_output):
        event = create_run_content_completed_event(mock_run_output)
        assert event.content == mock_run_output.content

    def test_session_id_copied(self, mock_run_output):
        event = create_run_content_completed_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_run_id_copied(self, mock_run_output):
        event = create_run_content_completed_event(mock_run_output)
        assert event.run_id == "run-001"

    def test_agent_name_copied(self, mock_run_output):
        event = create_run_content_completed_event(mock_run_output)
        assert event.agent_name == "TestAgent"


# ---------------------------------------------------------------------------
# create_run_output_content_event() tests
# ---------------------------------------------------------------------------


class TestCreateRunOutputContentEvent:
    def test_returns_run_content_event(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output)
        assert isinstance(event, RunContentEvent)

    def test_event_type_is_run_content(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output)
        assert event.event == RunEvent.run_content.value

    def test_session_id_copied(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_content_passed(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output, content="Hello there!")
        assert event.content == "Hello there!"

    def test_content_type_defaults_to_str(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output)
        assert event.content_type == "str"

    def test_content_type_passed(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output, content_type="html")
        assert event.content_type == "html"

    def test_reasoning_content_combined(self, mock_run_output):
        event = create_run_output_content_event(
            mock_run_output,
            reasoning_content="Part A",
            redacted_reasoning_content="Part B",
        )
        # thinking_combined = reasoning_content + redacted_reasoning_content
        assert event.reasoning_content == "Part APart B"

    def test_reasoning_content_only(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output, reasoning_content="Only reasoning")
        assert event.reasoning_content == "Only reasoning"

    def test_redacted_only_combined(self, mock_run_output):
        event = create_run_output_content_event(
            mock_run_output, redacted_reasoning_content="Redacted only"
        )
        assert event.reasoning_content == "Redacted only"

    def test_no_reasoning_content_results_in_empty_string(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output)
        assert event.reasoning_content == ""

    def test_citations_passed(self, mock_run_output, citations_obj):
        event = create_run_output_content_event(mock_run_output, citations=citations_obj)
        assert event.citations is citations_obj

    def test_model_provider_data_passed(self, mock_run_output):
        event = create_run_output_content_event(
            mock_run_output, model_provider_data={"usage": {"tokens": 100}}
        )
        assert event.model_provider_data == {"usage": {"tokens": 100}}

    def test_references_from_run_output(self, mock_run_output):
        from ii_agent.agent.runtime.models.message import MessageReferences
        refs = [MessageReferences(query="q")]
        mock_run_output.references = refs
        event = create_run_output_content_event(mock_run_output)
        assert event.references is refs

    def test_additional_input_from_run_output(self, mock_run_output):
        msgs = [Message(role="user", content="extra")]
        mock_run_output.additional_input = msgs
        event = create_run_output_content_event(mock_run_output)
        assert event.additional_input is msgs

    def test_run_id_copied(self, mock_run_output):
        event = create_run_output_content_event(mock_run_output)
        assert event.run_id == "run-001"


# ---------------------------------------------------------------------------
# handle_event() tests
# ---------------------------------------------------------------------------


class TestHandleEvent:
    def test_returns_same_event(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        result = handle_event(event, mock_run_output)
        assert result is event

    def test_event_not_in_skip_list_is_returned(self, mock_run_output):
        event = create_run_started_event(mock_run_output)
        # Not in skip list -> returned as-is
        result = handle_event(event, mock_run_output, events_to_skip=[RunEvent.run_completed])
        assert result is event

    def test_event_in_skip_list_is_still_returned(self, mock_run_output):
        """Event in skip list is returned but not persisted."""
        event = create_run_started_event(mock_run_output)
        result = handle_event(
            event, mock_run_output, events_to_skip=[RunEvent.run_started]
        )
        # Still returns the event
        assert result is event

    def test_no_events_to_skip_processes_all_events(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        result = handle_event(event, mock_run_output, events_to_skip=None)
        assert result is event

    def test_empty_events_to_skip_processes_all(self, mock_run_output):
        event = create_run_completed_event(mock_run_output)
        result = handle_event(event, mock_run_output, events_to_skip=[])
        assert result is event

    def test_store_events_false_does_not_create_task(self, mock_run_output):
        """When store_events=False, asyncio.create_task should not be called."""
        event = create_run_started_event(mock_run_output)
        with patch("ii_agent.agent.runtime.run.events.asyncio.create_task") as mock_create_task:
            handle_event(event, mock_run_output, store_events=False)
            mock_create_task.assert_not_called()

    def test_store_events_true_creates_task_when_not_skipped(self, mock_run_output):
        """When store_events=True and event not in skip list, asyncio.create_task is called."""
        event = create_run_started_event(mock_run_output)
        with patch("ii_agent.agent.runtime.run.events.asyncio.create_task") as mock_create_task:
            handle_event(event, mock_run_output, store_events=True)
            mock_create_task.assert_called_once()

    def test_store_events_true_skips_task_when_event_in_skip_list(self, mock_run_output):
        """When event is in skip list, asyncio.create_task should not be called even with store_events=True."""
        event = create_run_started_event(mock_run_output)
        with patch("ii_agent.agent.runtime.run.events.asyncio.create_task") as mock_create_task:
            handle_event(
                event,
                mock_run_output,
                events_to_skip=[RunEvent.run_started],
                store_events=True,
            )
            mock_create_task.assert_not_called()

    def test_handle_event_with_error_event(self, mock_run_output):
        event = create_run_error_event(mock_run_output, error="boom")
        result = handle_event(event, mock_run_output)
        assert result is event
        assert isinstance(result, RunErrorEvent)

    def test_handle_event_with_tool_call_event(self, mock_run_output, tool_execution):
        event = create_tool_call_started_event(mock_run_output, tool=tool_execution)
        result = handle_event(event, mock_run_output)
        assert result is event

    def test_handle_event_skip_list_accepts_multiple_events(self, mock_run_output):
        event = create_run_content_delta_event(mock_run_output, content="delta")
        result = handle_event(
            event,
            mock_run_output,
            events_to_skip=[RunEvent.run_started, RunEvent.run_content_delta, RunEvent.run_completed],
        )
        assert result is event


# ---------------------------------------------------------------------------
# Session summary event tests
# ---------------------------------------------------------------------------


class TestSessionSummaryEvents:
    def test_create_session_summary_started_event_type(self, mock_run_output):
        from ii_agent.agent.runtime.run.events import create_session_summary_started_event
        event = create_session_summary_started_event(mock_run_output)
        assert isinstance(event, AgentSummaryStartedEvent)
        assert event.event == RunEvent.session_summary_started.value

    def test_create_session_summary_started_copies_session_id(self, mock_run_output):
        from ii_agent.agent.runtime.run.events import create_session_summary_started_event
        event = create_session_summary_started_event(mock_run_output)
        assert event.session_id == "session-abc"

    def test_create_session_summary_completed_event_type(self, mock_run_output):
        from ii_agent.agent.runtime.run.events import create_session_summary_completed_event
        event = create_session_summary_completed_event(mock_run_output)
        assert isinstance(event, AgentSummaryCompletedEvent)
        assert event.event == RunEvent.session_summary_completed.value

    def test_create_session_summary_completed_with_summary(self, mock_run_output):
        from ii_agent.agent.runtime.run.events import create_session_summary_completed_event
        mock_summary = MagicMock()
        event = create_session_summary_completed_event(mock_run_output, session_summary=mock_summary)
        assert event.session_summary is mock_summary

    def test_create_session_summary_completed_none_summary_by_default(self, mock_run_output):
        from ii_agent.agent.runtime.run.events import create_session_summary_completed_event
        event = create_session_summary_completed_event(mock_run_output)
        assert event.session_summary is None


# ---------------------------------------------------------------------------
# Event field consistency tests
# ---------------------------------------------------------------------------


class TestEventFieldConsistency:
    """Verify that all events share the same base fields from RunOutput."""

    def _get_all_events(self, run_output, tool_exec):
        """Collect one instance of every event type we create."""
        return [
            create_run_started_event(run_output),
            create_run_completed_event(run_output),
            create_run_paused_event(run_output),
            create_run_error_event(run_output, error="e"),
            create_run_cancelled_event(run_output, reason="r"),
            create_pre_hook_started_event(run_output),
            create_pre_hook_completed_event(run_output),
            create_post_hook_started_event(run_output),
            create_post_hook_completed_event(run_output),
            create_memory_update_started_event(run_output),
            create_memory_update_completed_event(run_output),
            create_reasoning_started_event(run_output),
            create_reasoning_delta_event(run_output),
            create_reasoning_completed_event(run_output),
            create_tool_call_started_event(run_output, tool=tool_exec),
            create_tool_call_completed_event(run_output, tool=tool_exec),
            create_run_content_delta_event(run_output),
            create_run_content_completed_event(run_output),
            create_run_output_content_event(run_output),
        ]

    def test_all_events_have_session_id(self, mock_run_output, tool_execution):
        for event in self._get_all_events(mock_run_output, tool_execution):
            assert event.session_id == "session-abc", f"Missing session_id in {type(event).__name__}"

    def test_all_events_have_run_id(self, mock_run_output, tool_execution):
        for event in self._get_all_events(mock_run_output, tool_execution):
            assert event.run_id == "run-001", f"Missing run_id in {type(event).__name__}"

    def test_all_events_have_agent_name(self, mock_run_output, tool_execution):
        for event in self._get_all_events(mock_run_output, tool_execution):
            assert event.agent_name == "TestAgent", f"Missing agent_name in {type(event).__name__}"

    def test_all_events_have_model(self, mock_run_output, tool_execution):
        for event in self._get_all_events(mock_run_output, tool_execution):
            assert event.model == "gpt-4o", f"Missing model in {type(event).__name__}"

    def test_all_events_have_event_string(self, mock_run_output, tool_execution):
        for event in self._get_all_events(mock_run_output, tool_execution):
            assert isinstance(event.event, str), f"event field not str in {type(event).__name__}"
            assert len(event.event) > 0, f"Empty event string in {type(event).__name__}"
