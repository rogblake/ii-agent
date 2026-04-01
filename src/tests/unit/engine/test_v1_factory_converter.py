"""Unit tests for agent event → realtime event conversion.

Tests cover:
- convert_agent_event_to_realtime produces correct BaseEvent subclasses
- to_socket_payload includes the ``type`` field matching the dotted ``name``
- EventType enum values match BaseEvent.name on every subclass
"""

from __future__ import annotations

import uuid

import pytest

from ii_agent.realtime.events.app_events import (
    EventGroup,
    EventType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SESSION_STR = str(SESSION_UUID)
RUN_ID_STR = "11111111-2222-3333-4444-555555555555"


def _make_event(cls_name: str, **overrides):
    """Build a runtime event by class name with sensible defaults."""
    import importlib

    mod = importlib.import_module("ii_agent.agents.runs.agent")
    cls = getattr(mod, cls_name)
    defaults = dict(
        agent_id="agent-1",
        agent_name="TestAgent",
        run_id=RUN_ID_STR,
        session_id=SESSION_STR,
    )
    defaults.update(overrides)
    return cls(**defaults)


# ---------------------------------------------------------------------------
# Runtime event construction
# ---------------------------------------------------------------------------


class TestRuntimeEvents:
    """Runtime agent events can be constructed and serialised."""

    def test_run_started_has_event_field(self):
        event = _make_event("RunStartedEvent")
        assert event.event == "RunStarted"

    def test_run_completed_has_event_field(self):
        event = _make_event("RunCompletedEvent")
        assert event.event == "RunCompleted"

    def test_run_error_has_event_field(self):
        event = _make_event("RunErrorEvent")
        assert event.event == "RunError"

    def test_run_started_to_dict_contains_model(self):
        event = _make_event("RunStartedEvent", model="claude-3-opus")
        d = event.to_dict()
        assert d["model"] == "claude-3-opus"

    def test_run_content_to_dict_contains_content(self):
        event = _make_event("RunContentEvent", content="Hello")
        d = event.to_dict()
        assert d["content"] == "Hello"

    def test_run_error_to_dict_contains_error_type(self):
        event = _make_event("RunErrorEvent", error_type="RuntimeError", content="fail")
        d = event.to_dict()
        assert d["error_type"] == "RuntimeError"

    def test_reasoning_delta_to_dict_contains_reasoning(self):
        event = _make_event(
            "ReasoningDeltaEvent",
            reasoning_content="Thinking...",
            is_redacted=False,
        )
        d = event.to_dict()
        assert d["reasoning_content"] == "Thinking..."


# ---------------------------------------------------------------------------
# convert_agent_event_to_realtime
# ---------------------------------------------------------------------------


class TestConvertAgentEventToRealtime:
    """convert_agent_event_to_realtime maps runtime events to BaseEvent subclasses."""

    def test_run_started_produces_processing_event(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunStartedEvent", model="gpt-4o")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)

        assert result is not None
        assert result.group == EventGroup.AGENT
        assert result.name == "agent.processing"
        assert result.content["model"] == "gpt-4o"

    def test_run_content_produces_agent_response(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunContentEvent", content="Hello world")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)

        assert result is not None
        assert result.name == "agent.response"
        assert result.content["text"] == "Hello world"

    def test_run_error_produces_system_error(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunErrorEvent", error_type="RuntimeError", content="fail")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)

        assert result is not None
        assert result.name == "system.error"
        assert result.content["error_code"] == "execution_error"
        assert result.content["message"] == "fail"

    def test_run_cancelled_produces_interrupted(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunCancelledEvent", reason="User cancelled")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)

        assert result is not None
        assert result.name == "agent.response.interrupted"

    def test_session_summary_started_returns_none(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("AgentSummaryStartedEvent")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)
        assert result is None

    def test_session_summary_completed_produces_model_compact(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("AgentSummaryCompletedEvent")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)

        assert result is not None
        assert result.name == "agent.model.compact"

    def test_string_session_id_accepted(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunStartedEvent", model="gpt-4o")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_STR)

        assert result is not None
        assert result.session_id == SESSION_UUID


# ---------------------------------------------------------------------------
# to_socket_payload includes ``type`` field
# ---------------------------------------------------------------------------


class TestToSocketPayload:
    """BaseEvent.to_socket_payload() uses ``name`` as the FE dispatch key."""

    def test_processing_event_has_name(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunStartedEvent", model="gpt-4o")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)
        payload = result.to_socket_payload()

        assert payload["name"] == "agent.processing"
        assert "type" not in payload

    def test_agent_response_has_name(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunContentEvent", content="Hello")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)
        payload = result.to_socket_payload()

        assert payload["name"] == "agent.response"
        assert "type" not in payload

    def test_error_event_has_name(self):
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunErrorEvent", error_type="RuntimeError", content="fail")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)
        payload = result.to_socket_payload()

        assert payload["name"] == "system.error"
        assert "type" not in payload


# ---------------------------------------------------------------------------
# EventType values == BaseEvent.name (no mapping layer)
# ---------------------------------------------------------------------------


class TestEventTypeMatchesName:
    """EventType enum values are the canonical dotted names used as ``type`` in payloads."""

    @pytest.mark.parametrize(
        "event_type,expected_dotted_name",
        [
            (EventType.PROCESSING, "agent.processing"),
            (EventType.AGENT_RESPONSE, "agent.response"),
            (EventType.AGENT_RESPONSE_DELTA, "agent.response.delta"),
            (EventType.COMPLETE, "agent.complete"),
            (EventType.TOOL_CALL, "agent.tool.call"),
            (EventType.TOOL_RESULT, "agent.tool.result"),
            (EventType.ERROR, "system.error"),
            (EventType.USER_MESSAGE, "session.user_message"),
            (EventType.CONNECTION_ESTABLISHED, "connection.established"),
            (EventType.SANDBOX_STATUS, "sandbox.status_changed"),
            (EventType.PLAN_GENERATED, "plan.milestone.generated"),
        ],
    )
    def test_enum_value_is_dotted_name(self, event_type: str, expected_dotted_name: str):
        assert event_type == expected_dotted_name

    def test_to_socket_payload_name_is_dispatch_key(self):
        """to_socket_payload() uses ``name`` as the FE dispatch key (no ``type``)."""
        from ii_agent.realtime.events.converter import convert_agent_event_to_realtime

        event = _make_event("RunStartedEvent", model="gpt-4o")
        result = convert_agent_event_to_realtime(event, session_id=SESSION_UUID)
        payload = result.to_socket_payload()

        assert payload["name"] == result.name
        assert "type" not in payload
