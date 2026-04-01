"""Unit tests for ii_agent/agent/runtime/models/base.py (actually run/base.py).

Tests cover:
- RunStatus enum values and helper methods
- RunContext dataclass creation and fields
- BaseRunOutputEvent.to_dict() and to_json()
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# RunStatus (from engine.agents.models - re-exported through run/base)
# ---------------------------------------------------------------------------


class TestRunStatus:
    """Tests for the RunStatus enum."""

    def test_pending_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.PENDING.value == "pending"

    def test_running_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.RUNNING.value == "running"

    def test_completed_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.COMPLETED.value == "completed"

    def test_paused_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.PAUSED.value == "paused"

    def test_aborted_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.ABORTED.value == "aborted"

    def test_failed_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.FAILED.value == "failed"

    def test_error_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.ERROR.value == "error"

    def test_aborting_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.ABORTING.value == "aborting"

    def test_system_interrupted_value(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.SYSTEM_INTERRUPTED.value == "system_interrupted"

    def test_from_string_case_insensitive(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.from_string("RUNNING") == RunStatus.RUNNING
        assert RunStatus.from_string("Running") == RunStatus.RUNNING

    def test_from_string_completed(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.from_string("completed") == RunStatus.COMPLETED

    def test_from_string_unknown_defaults_to_running(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.from_string("totally_unknown") == RunStatus.RUNNING

    def test_runable_states_contains_running(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.RUNNING in RunStatus.runable_states()

    def test_runable_states_contains_paused(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.PAUSED in RunStatus.runable_states()

    def test_runable_states_contains_aborting(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.ABORTING in RunStatus.runable_states()

    def test_runable_states_does_not_contain_completed(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.COMPLETED not in RunStatus.runable_states()

    def test_runable_states_does_not_contain_failed(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.FAILED not in RunStatus.runable_states()

    def test_is_string_enum(self):
        from ii_agent.agents.runs.models import RunStatus

        assert RunStatus.RUNNING == "running"

    def test_status_comparison_with_string(self):
        from ii_agent.agents.runs.models import RunStatus

        status = RunStatus.COMPLETED
        assert status == "completed"


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------


class TestRunContext:
    """Tests for the RunContext dataclass."""

    def test_create_with_required_fields(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id="r1", session_id="s1", user_id="u1")
        assert ctx.run_id == "r1"
        assert ctx.session_id == "s1"
        assert ctx.user_id == "u1"

    def test_dependencies_defaults_to_none(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id="r1", session_id="s1", user_id="u1")
        assert ctx.dependencies is None

    def test_metadata_defaults_to_none(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id="r1", session_id="s1", user_id="u1")
        assert ctx.metadata is None

    def test_session_state_defaults_to_none(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id="r1", session_id="s1", user_id="u1")
        assert ctx.session_state is None

    def test_output_schema_defaults_to_none(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id="r1", session_id="s1", user_id="u1")
        assert ctx.output_schema is None

    def test_run_id_can_be_none(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id=None, session_id="s1", user_id="u1")
        assert ctx.run_id is None

    def test_all_fields_can_be_none(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(run_id=None, session_id=None, user_id=None)
        assert ctx.run_id is None
        assert ctx.session_id is None
        assert ctx.user_id is None

    def test_create_with_metadata(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(
            run_id="r1",
            session_id="s1",
            user_id="u1",
            metadata={"source": "test"},
        )
        assert ctx.metadata == {"source": "test"}

    def test_create_with_dependencies(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(
            run_id="r1",
            session_id="s1",
            user_id="u1",
            dependencies={"db": "mock_db"},
        )
        assert ctx.dependencies == {"db": "mock_db"}

    def test_create_with_session_state(self):
        from ii_agent.agents.runs.base import RunContext

        ctx = RunContext(
            run_id="r1",
            session_id="s1",
            user_id="u1",
            session_state={"step": 3},
        )
        assert ctx.session_state == {"step": 3}


# ---------------------------------------------------------------------------
# BaseRunOutputEvent
# ---------------------------------------------------------------------------


class TestBaseRunOutputEvent:
    """Tests for BaseRunOutputEvent.to_dict() / to_json() / properties."""

    def _make_event(self, **kwargs):
        from ii_agent.agents.runs.agent import RunStartedEvent

        defaults = dict(agent_id="a1", agent_name="Agent")
        defaults.update(kwargs)
        return RunStartedEvent(**defaults)

    def test_to_dict_returns_dict(self):
        ev = self._make_event()
        result = ev.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_excludes_none_values(self):
        ev = self._make_event(run_id=None, parent_run_id=None)
        result = ev.to_dict()
        assert "run_id" not in result or result.get("run_id") is not None

    def test_to_dict_includes_event_field(self):
        ev = self._make_event()
        result = ev.to_dict()
        assert "event" in result
        assert result["event"] == "RunStarted"

    def test_to_dict_includes_agent_name(self):
        ev = self._make_event(agent_name="MyAgent")
        result = ev.to_dict()
        assert result["agent_name"] == "MyAgent"

    def test_to_json_returns_valid_json_string(self):
        import json

        ev = self._make_event(agent_name="MyAgent")
        json_str = ev.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["agent_name"] == "MyAgent"

    def test_to_json_with_indent_none(self):
        import json

        ev = self._make_event()
        json_str = ev.to_json(indent=None)
        parsed = json.loads(json_str)
        assert "event" in parsed

    def test_is_paused_property_is_false(self):
        ev = self._make_event()
        assert ev.is_paused is False

    def test_is_cancelled_property_is_false(self):
        ev = self._make_event()
        assert ev.is_cancelled is False

    def test_to_dict_does_not_include_tools_key_when_none(self):
        ev = self._make_event()
        result = ev.to_dict()
        # tools=None should not appear (excluded in base)
        assert "tools" not in result or result.get("tools") is not None

    def test_to_dict_with_run_id_set(self):
        ev = self._make_event(run_id="run-abc")
        result = ev.to_dict()
        assert result.get("run_id") == "run-abc"

    def test_to_dict_excludes_image_when_none(self):
        from ii_agent.agents.runs.agent import RunContentEvent

        ev = RunContentEvent(agent_id="a1", agent_name="A", image=None)
        result = ev.to_dict()
        assert "image" not in result
