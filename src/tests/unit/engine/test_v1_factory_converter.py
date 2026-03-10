"""Unit tests for ii_agent/agent/runtime/factory/converter.py.

Tests cover:
- convert_agent_event_to_realtime() for every supported event type
- _get_sub_agent_info() with and without sub-agent fields
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers to build lightweight events without pulling heavy agent deps
# ---------------------------------------------------------------------------

SESSION_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SESSION_STR = str(SESSION_UUID)
RUN_ID_STR = "11111111-2222-3333-4444-555555555555"


def _make_run_started(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunStartedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        model="claude-3-opus",
        model_provider="anthropic",
    )
    defaults.update(kwargs)
    return RunStartedEvent(**defaults)


def _make_run_content(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunContentEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        content="Hello from agent",
        image=None,
        citations=None,
    )
    defaults.update(kwargs)
    return RunContentEvent(**defaults)


def _make_run_completed(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunCompletedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
    )
    defaults.update(kwargs)
    return RunCompletedEvent(**defaults)


def _make_run_error(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunErrorEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        content="Something broke",
        error_type="RuntimeError",
        error_id="err-001",
        additional_data=None,
    )
    defaults.update(kwargs)
    return RunErrorEvent(**defaults)


def _make_run_cancelled(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunCancelledEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        reason="User cancelled",
    )
    defaults.update(kwargs)
    return RunCancelledEvent(**defaults)


def _make_run_paused(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunPausedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        tools=None,
        requirements=None,
    )
    defaults.update(kwargs)
    return RunPausedEvent(**defaults)


def _make_run_continued(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunContinuedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
    )
    defaults.update(kwargs)
    return RunContinuedEvent(**defaults)


def _make_reasoning_started(**kwargs):
    from ii_agent.agent.runtime.run.agent import ReasoningStartedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
    )
    defaults.update(kwargs)
    return ReasoningStartedEvent(**defaults)


def _make_reasoning_delta(**kwargs):
    from ii_agent.agent.runtime.run.agent import ReasoningDeltaEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        reasoning_content="Thinking...",
        redacted_reasoning_content=None,
        is_redacted=False,
    )
    defaults.update(kwargs)
    return ReasoningDeltaEvent(**defaults)


def _make_reasoning_completed(**kwargs):
    from ii_agent.agent.runtime.run.agent import ReasoningCompletedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        content="Final reasoning",
    )
    defaults.update(kwargs)
    return ReasoningCompletedEvent(**defaults)


def _make_content_delta(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunContentDeltaEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        content="token chunk",
    )
    defaults.update(kwargs)
    return RunContentDeltaEvent(**defaults)


def _make_session_summary_started(**kwargs):
    from ii_agent.agent.runtime.run.agent import SessionSummaryStartedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
    )
    defaults.update(kwargs)
    return SessionSummaryStartedEvent(**defaults)


def _make_session_summary_completed(**kwargs):
    from ii_agent.agent.runtime.run.agent import SessionSummaryCompletedEvent

    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        session_summary=None,
    )
    defaults.update(kwargs)
    return SessionSummaryCompletedEvent(**defaults)


def _make_run_output(**kwargs):
    from ii_agent.agent.runtime.run.agent import RunOutput
    from ii_agent.agent.runtime.run.base import RunStatus

    defaults = dict(
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
        user_id="user-1",
        model="claude-3-opus",
        agent_name="TestAgent",
        status=RunStatus.COMPLETED,
        content="Task completed",
    )
    defaults.update(kwargs)
    return RunOutput(**defaults)


# ---------------------------------------------------------------------------
# _get_sub_agent_info
# ---------------------------------------------------------------------------

class TestGetSubAgentInfo:
    """Tests for _get_sub_agent_info helper function."""

    def test_returns_dict_with_agent_name_for_plain_event(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        # A plain non-sub-agent event still carries agent_name (always included when set)
        event = _make_run_started(agent_name="TestAgent")
        result = _get_sub_agent_info(event)
        # delegated_from / is_sub_agent_event / parent_run_id should NOT be present
        assert "delegated_from" not in result
        assert "is_sub_agent_event" not in result
        assert "parent_run_id" not in result

    def test_includes_delegated_from_when_set(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        event = _make_run_started(delegated_from="ParentAgent")
        result = _get_sub_agent_info(event)
        assert result.get("delegated_from") == "ParentAgent"

    def test_includes_is_sub_agent_event_when_true(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        event = _make_run_started(is_sub_agent_event=True)
        result = _get_sub_agent_info(event)
        assert result.get("is_sub_agent_event") is True

    def test_excludes_is_sub_agent_event_when_false(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        event = _make_run_started(is_sub_agent_event=False)
        result = _get_sub_agent_info(event)
        assert "is_sub_agent_event" not in result

    def test_includes_parent_run_id_when_set(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        event = _make_run_started(parent_run_id="parent-run-123")
        result = _get_sub_agent_info(event)
        assert result.get("parent_run_id") == "parent-run-123"

    def test_includes_agent_name_when_set(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        event = _make_run_started(agent_name="SubAgent")
        result = _get_sub_agent_info(event)
        assert result.get("agent_name") == "SubAgent"

    def test_run_output_is_sub_agent_response_included(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        output = _make_run_output(delegated_from="ParentAgent")
        result = _get_sub_agent_info(output)
        assert result.get("is_sub_agent_response") is True

    def test_run_output_non_sub_agent_excludes_is_sub_agent_response(self):
        from ii_agent.agent.runtime.factory.converter import _get_sub_agent_info

        output = _make_run_output()
        result = _get_sub_agent_info(output)
        assert "is_sub_agent_response" not in result


# ---------------------------------------------------------------------------
# convert_agent_event_to_realtime
# ---------------------------------------------------------------------------

class TestConvertAgentEventToRealtime:
    """Tests for convert_agent_event_to_realtime()."""

    # --- RunOutput (non-aborted) ---
    def test_run_output_completed_returns_complete_event(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        output = _make_run_output()
        realtime = convert_agent_event_to_realtime(output, SESSION_STR)
        assert realtime is not None
        assert realtime.type == EventType.COMPLETE

    def test_run_output_completed_has_correct_session_id(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        output = _make_run_output()
        realtime = convert_agent_event_to_realtime(output, SESSION_STR)
        assert realtime.session_id == SESSION_UUID

    def test_run_output_completed_content_has_text(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        output = _make_run_output(content="Finished processing")
        realtime = convert_agent_event_to_realtime(output, SESSION_STR)
        assert realtime.content["text"] == "Finished processing"

    def test_run_output_aborted_returns_interrupted_event(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.agent.runtime.run.base import RunStatus
        from ii_agent.core.events.models import EventType

        output = _make_run_output(status=RunStatus.ABORTED)
        realtime = convert_agent_event_to_realtime(output, SESSION_STR)
        assert realtime.type == EventType.AGENT_RESPONSE_INTERRUPTED

    def test_run_output_sub_agent_returns_sub_agent_complete(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        output = _make_run_output(delegated_from="ParentAgent")
        realtime = convert_agent_event_to_realtime(output, SESSION_STR)
        assert realtime.type == EventType.SUB_AGENT_COMPLETE

    # --- RunStartedEvent ---
    def test_run_started_returns_processing_event(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_started()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime is not None
        assert realtime.type == EventType.PROCESSING

    def test_run_started_content_has_model(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_started(model="gpt-4o")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["model"] == "gpt-4o"

    def test_run_started_content_has_model_provider(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_started(model_provider="openai")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["model_provider"] == "openai"

    def test_run_started_content_has_agent_name(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_started(agent_name="MyAgent")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["agent_name"] == "MyAgent"

    def test_run_started_with_uuid_session_id(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_started()
        realtime = convert_agent_event_to_realtime(event, SESSION_UUID)
        assert realtime.session_id == SESSION_UUID

    # --- RunContentEvent ---
    def test_run_content_returns_agent_response(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_content()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.AGENT_RESPONSE

    def test_run_content_text_in_content(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_content(content="Some agent text")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["text"] == "Some agent text"

    # --- RunCompletedEvent ---
    def test_run_completed_returns_complete_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_completed()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.COMPLETE

    def test_run_completed_as_sub_agent_returns_sub_agent_complete(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_completed(is_sub_agent_event=True)
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.SUB_AGENT_COMPLETE

    # --- RunErrorEvent ---
    def test_run_error_returns_error_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_error()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.ERROR

    def test_run_error_content_has_message(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_error(content="Connection failed")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["message"] == "Connection failed"

    def test_run_error_content_has_error_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_error(error_type="TimeoutError")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["error_type"] == "TimeoutError"

    def test_run_error_content_has_error_id(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_error(error_id="err-xyz")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["error_id"] == "err-xyz"

    def test_run_error_none_message_defaults_to_string(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_error(content=None)
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert isinstance(realtime.content["message"], str)

    # --- RunCancelledEvent ---
    def test_run_cancelled_returns_interrupted_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_cancelled()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.AGENT_RESPONSE_INTERRUPTED

    def test_run_cancelled_content_has_message(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_cancelled(reason="User pressed stop")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["message"] == "User pressed stop"

    def test_run_cancelled_no_reason_defaults(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_cancelled(reason=None)
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert isinstance(realtime.content["message"], str)

    # --- RunPausedEvent ---
    def test_run_paused_returns_tool_confirmation_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_paused()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.TOOL_CONFIRMATION

    def test_run_paused_content_has_tools_list(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_paused()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert "tools" in realtime.content

    # --- RunContinuedEvent ---
    def test_run_continued_returns_processing_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_run_continued()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.PROCESSING

    def test_run_continued_content_message(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_continued()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert "resumed" in realtime.content["message"].lower()

    # --- ReasoningStartedEvent ---
    def test_reasoning_started_returns_agent_thinking_start(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_reasoning_started()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.AGENT_THINKING_START

    # --- ReasoningDeltaEvent ---
    def test_reasoning_delta_returns_agent_thinking_delta(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_reasoning_delta()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.AGENT_THINKING_DELTA

    def test_reasoning_delta_non_redacted_uses_reasoning_content(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_reasoning_delta(reasoning_content="I am thinking", is_redacted=False)
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["text"] == "I am thinking"

    def test_reasoning_delta_redacted_uses_redacted_content(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_reasoning_delta(
            is_redacted=True,
            redacted_reasoning_content="<encrypted>",
            reasoning_content="plain",
        )
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["text"] == "<encrypted>"

    # --- ReasoningCompletedEvent ---
    def test_reasoning_completed_returns_agent_thinking_type(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_reasoning_completed()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.AGENT_THINKING

    def test_reasoning_completed_content_has_text(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_reasoning_completed(content="Final thought")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["text"] == "Final thought"

    # --- RunContentDeltaEvent ---
    def test_content_delta_returns_agent_response_delta(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_content_delta()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.AGENT_RESPONSE_DELTA

    def test_content_delta_has_text_in_content(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_content_delta(content="chunk")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["text"] == "chunk"

    # --- SessionSummaryStartedEvent ---
    def test_session_summary_started_returns_none(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_session_summary_started()
        result = convert_agent_event_to_realtime(event, SESSION_STR)
        assert result is None

    # --- SessionSummaryCompletedEvent ---
    def test_session_summary_completed_returns_model_compact(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime
        from ii_agent.core.events.models import EventType

        event = _make_session_summary_completed()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.type == EventType.MODEL_COMPACT

    def test_session_summary_completed_content_has_status(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_session_summary_completed()
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime.content["status"] == "compacted"

    # --- Unknown event ---
    def test_unknown_event_type_returns_none(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        class UnknownEvent:
            run_id = None
            event = "UnknownEvent"

        result = convert_agent_event_to_realtime(UnknownEvent(), SESSION_STR)
        assert result is None

    # --- run_id parsing ---
    def test_invalid_run_id_does_not_crash(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_started(run_id="not-a-uuid")
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        # Should still return a valid event; run_id may be None
        assert realtime is not None

    def test_none_run_id_does_not_crash(self):
        from ii_agent.agent.runtime.factory.converter import convert_agent_event_to_realtime

        event = _make_run_started(run_id=None)
        realtime = convert_agent_event_to_realtime(event, SESSION_STR)
        assert realtime is not None
