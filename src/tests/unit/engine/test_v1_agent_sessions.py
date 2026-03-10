"""Unit tests for engine/runtime/agent_sessions/ - AgentSession, SessionSummary, SessionStore."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from ii_agent.engine.runtime.agent_sessions.agent import AgentSession
from ii_agent.engine.runtime.agent_sessions.base import NoOpSessionStore
from ii_agent.engine.runtime.agent_sessions.summary import (
    DEFAULT_TOKEN_THRESHOLD,
    MODEL_TOKEN_THRESHOLDS,
    SessionSummary,
    SessionSummaryManager,
    SessionSummaryResponse,
)
from ii_agent.engine.runtime.run.base import RunStatus


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_run_output(
    run_id: str = "run-1",
    status: RunStatus = RunStatus.COMPLETED,
    messages: Optional[List] = None,
):
    """Create a minimal RunOutput-like object using SimpleNamespace."""
    from types import SimpleNamespace

    run = SimpleNamespace(
        run_id=run_id,
        status=status,
        messages=messages or [],
    )
    run.to_dict = lambda: {"run_id": run_id, "status": status.value, "messages": []}
    return run


def _make_session(
    session_id: str = "sess-1",
    user_id: str = "user-1",
    runs=None,
) -> AgentSession:
    return AgentSession(
        session_id=session_id,
        user_id=user_id,
        runs=runs if runs is not None else [],
    )


# ---------------------------------------------------------------------------
# AgentSession construction tests
# ---------------------------------------------------------------------------


class TestAgentSessionConstruction:
    """Tests for AgentSession dataclass."""

    def test_basic_construction(self):
        session = AgentSession(session_id="s1", user_id="u1")
        assert session.session_id == "s1"
        assert session.user_id == "u1"

    def test_optional_fields_default_none(self):
        session = AgentSession(session_id="s1", user_id="u1")
        assert session.agent_id is None
        assert session.session_data is None
        assert session.metadata is None
        assert session.agent_data is None
        assert session.summary is None
        assert session.created_at is None
        assert session.updated_at is None

    def test_runs_default_empty_list(self):
        session = AgentSession(session_id="s1", user_id="u1", runs=[])
        assert session.runs == []

    def test_with_all_fields(self):
        session = AgentSession(
            session_id="s1",
            user_id="u1",
            agent_id="agent-1",
            session_data={"key": "value"},
            metadata={"extra": "data"},
            agent_data={"name": "my-agent"},
            created_at=1000000,
            updated_at=1000001,
        )
        assert session.agent_id == "agent-1"
        assert session.session_data == {"key": "value"}
        assert session.metadata == {"extra": "data"}
        assert session.created_at == 1000000


# ---------------------------------------------------------------------------
# AgentSession add_run / get_run tests
# ---------------------------------------------------------------------------


class TestAgentSessionRunManagement:
    """Tests for add_run and get_run methods."""

    def test_add_run_to_empty_session(self):
        session = _make_session()
        run = _make_run_output(run_id="run-1")
        session.add_run(run)
        assert len(session.runs) == 1

    def test_add_run_updates_existing(self):
        session = _make_session()
        run1 = _make_run_output(run_id="run-1")
        session.add_run(run1)
        run1_updated = _make_run_output(run_id="run-1")
        session.add_run(run1_updated)
        # Should still be 1 run (updated in place)
        assert len(session.runs) == 1

    def test_add_different_runs(self):
        session = _make_session()
        run1 = _make_run_output(run_id="run-1")
        run2 = _make_run_output(run_id="run-2")
        session.add_run(run1)
        session.add_run(run2)
        assert len(session.runs) == 2

    def test_get_run_existing(self):
        session = _make_session()
        run = _make_run_output(run_id="run-abc")
        session.add_run(run)
        result = session.get_run("run-abc")
        assert result is not None
        assert result.run_id == "run-abc"

    def test_get_run_nonexistent_returns_none(self):
        session = _make_session()
        result = session.get_run("nonexistent")
        assert result is None

    def test_get_run_empty_session_returns_none(self):
        session = AgentSession(session_id="s1", user_id="u1")
        result = session.get_run("any")
        assert result is None


# ---------------------------------------------------------------------------
# AgentSession get_messages tests
# ---------------------------------------------------------------------------


class TestAgentSessionGetMessages:
    """Tests for get_messages method."""

    def _make_message(self, role: str, content: str = ""):
        from types import SimpleNamespace

        return SimpleNamespace(
            role=role,
            content=content,
            tool_calls=None,
            metrics=None,
            from_history=False,
        )

    def test_empty_runs_returns_empty_list(self):
        session = AgentSession(session_id="s1", user_id="u1")
        messages = session.get_messages()
        assert messages == []

    def test_runs_none_returns_empty_list(self):
        session = AgentSession(session_id="s1", user_id="u1", runs=None)
        messages = session.get_messages()
        assert messages == []

    def test_returns_messages_from_runs(self):
        from types import SimpleNamespace

        user_msg = self._make_message("user", "hello")
        asst_msg = self._make_message("assistant", "hi")

        run = SimpleNamespace(
            run_id="r1",
            status=RunStatus.COMPLETED,
            messages=[user_msg, asst_msg],
        )
        session = _make_session(runs=[run])
        messages = session.get_messages()
        assert len(messages) >= 2

    def test_skips_paused_run_messages(self):
        from types import SimpleNamespace

        user_msg = self._make_message("user", "query")
        paused_run = SimpleNamespace(
            run_id="r1",
            status=RunStatus.PAUSED,
            messages=[user_msg],
        )
        session = _make_session(runs=[paused_run])
        messages = session.get_messages()
        assert len(messages) == 0

    def test_skip_roles_filters_messages(self):
        from types import SimpleNamespace

        user_msg = self._make_message("user", "hi")
        system_msg = self._make_message("system", "system prompt")

        run = SimpleNamespace(
            run_id="r1",
            status=RunStatus.COMPLETED,
            messages=[system_msg, user_msg],
        )
        session = _make_session(runs=[run])
        messages = session.get_messages(skip_roles=["system"])
        roles = [m.role for m in messages]
        assert "system" not in roles

    def test_get_chat_history_skips_system_and_tool(self):
        from types import SimpleNamespace

        user_msg = self._make_message("user", "hi")
        system_msg = self._make_message("system", "prompt")
        tool_msg = self._make_message("tool", "result")

        run = SimpleNamespace(
            run_id="r1",
            status=RunStatus.COMPLETED,
            messages=[system_msg, user_msg, tool_msg],
        )
        session = _make_session(runs=[run])
        chat_history = session.get_chat_history()
        roles = [m.role for m in chat_history]
        assert "system" not in roles
        assert "tool" not in roles


# ---------------------------------------------------------------------------
# AgentSession to_dict / from_dict tests
# ---------------------------------------------------------------------------


class TestAgentSessionSerialization:
    """Tests for to_dict and from_dict."""

    def test_to_dict_basic(self):
        session = AgentSession(session_id="s1", user_id="u1", runs=[])
        d = session.to_dict()
        assert d["session_id"] == "s1"
        assert d["user_id"] == "u1"

    def test_to_dict_no_runs_is_none(self):
        session = AgentSession(session_id="s1", user_id="u1", runs=[])
        d = session.to_dict()
        assert d["runs"] == [] or d["runs"] is None

    def test_from_dict_basic(self):
        data = {
            "session_id": "s2",
            "user_id": "u2",
        }
        session = AgentSession.from_dict(data)
        assert session is not None
        assert session.session_id == "s2"
        assert session.user_id == "u2"

    def test_from_dict_missing_session_id_returns_none(self):
        data = {"user_id": "u1"}
        result = AgentSession.from_dict(data)
        assert result is None

    def test_from_dict_missing_user_id_returns_none(self):
        data = {"session_id": "s1"}
        result = AgentSession.from_dict(data)
        assert result is None

    def test_from_dict_none_returns_none(self):
        result = AgentSession.from_dict({"session_id": None, "user_id": "u1"})
        assert result is None

    def test_from_dict_with_metadata(self):
        data = {
            "session_id": "s3",
            "user_id": "u3",
            "metadata": {"key": "value"},
        }
        session = AgentSession.from_dict(data)
        assert session is not None
        assert session.metadata == {"key": "value"}

    def test_get_session_summary_none_when_not_set(self):
        session = _make_session()
        assert session.get_session_summary() is None

    def test_get_session_summary_returns_summary(self):
        summary = SessionSummary(content="Test summary")
        session = _make_session()
        session.summary = summary
        result = session.get_session_summary()
        assert result is not None
        assert result.content == "Test summary"


# ---------------------------------------------------------------------------
# SessionSummary tests
# ---------------------------------------------------------------------------


class TestSessionSummary:
    """Tests for SessionSummary dataclass."""

    def test_basic_construction(self):
        summary = SessionSummary(content="This is a summary")
        assert summary.content == "This is a summary"
        assert summary.topics is None
        assert summary.updated_at is None
        assert summary.metrics is None

    def test_with_topics(self):
        summary = SessionSummary(content="Summary", topics=["Python", "Testing"])
        assert summary.topics == ["Python", "Testing"]

    def test_with_updated_at(self):
        now = datetime.now()
        summary = SessionSummary(content="Summary", updated_at=now)
        assert summary.updated_at == now

    def test_to_dict_basic(self):
        summary = SessionSummary(content="Content")
        d = summary.to_dict()
        assert d["content"] == "Content"

    def test_to_dict_excludes_none_values(self):
        summary = SessionSummary(content="Content")
        d = summary.to_dict()
        assert "topics" not in d
        assert "metrics" not in d
        assert "updated_at" not in d

    def test_to_dict_with_topics(self):
        summary = SessionSummary(content="Content", topics=["AI", "ML"])
        d = summary.to_dict()
        assert d["topics"] == ["AI", "ML"]

    def test_to_dict_updated_at_as_isoformat(self):
        now = datetime(2024, 1, 15, 10, 30, 0)
        summary = SessionSummary(content="Content", updated_at=now)
        d = summary.to_dict()
        assert "2024-01-15" in d["updated_at"]

    def test_from_dict_basic(self):
        data = {"content": "Summary content"}
        summary = SessionSummary.from_dict(data)
        assert summary.content == "Summary content"

    def test_from_dict_with_iso_datetime_string(self):
        data = {
            "content": "Summary",
            "updated_at": "2024-01-15T10:30:00",
        }
        summary = SessionSummary.from_dict(data)
        assert isinstance(summary.updated_at, datetime)

    def test_from_dict_with_topics(self):
        data = {"content": "Summary", "topics": ["topic1", "topic2"]}
        summary = SessionSummary.from_dict(data)
        assert summary.topics == ["topic1", "topic2"]


# ---------------------------------------------------------------------------
# SessionSummaryResponse tests
# ---------------------------------------------------------------------------


class TestSessionSummaryResponse:
    """Tests for SessionSummaryResponse Pydantic model."""

    def test_basic_construction(self):
        resp = SessionSummaryResponse(summary="This is the summary")
        assert resp.summary == "This is the summary"
        assert resp.topics is None

    def test_with_topics(self):
        resp = SessionSummaryResponse(summary="Summary", topics=["AI", "Python"])
        assert resp.topics == ["AI", "Python"]

    def test_summary_required(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SessionSummaryResponse()

    def test_to_dict(self):
        resp = SessionSummaryResponse(summary="Content", topics=["t1"])
        d = resp.to_dict()
        assert d["summary"] == "Content"
        assert d["topics"] == ["t1"]

    def test_to_json(self):
        resp = SessionSummaryResponse(summary="Content")
        j = resp.to_json()
        assert "Content" in j
        assert isinstance(j, str)

    def test_to_dict_excludes_none_topics(self):
        resp = SessionSummaryResponse(summary="Content")
        d = resp.to_dict()
        assert "topics" not in d


# ---------------------------------------------------------------------------
# SessionSummaryManager tests
# ---------------------------------------------------------------------------


class TestSessionSummaryManager:
    """Tests for SessionSummaryManager."""

    def test_get_token_threshold_explicit(self):
        manager = SessionSummaryManager(token_threshold=50000)
        from types import SimpleNamespace

        mock_model = SimpleNamespace(id="unknown-model")
        manager.model = mock_model
        threshold = manager._get_token_threshold("any-model")
        assert threshold == 50000

    def test_get_token_threshold_from_model_map(self):
        manager = SessionSummaryManager()
        threshold = manager._get_token_threshold("gpt-4o")
        assert threshold == MODEL_TOKEN_THRESHOLDS["gpt-4o"]

    def test_get_token_threshold_default_for_unknown_model(self):
        manager = SessionSummaryManager()
        threshold = manager._get_token_threshold("unknown-model-xyz")
        assert threshold == DEFAULT_TOKEN_THRESHOLD

    def test_default_summary_request_message(self):
        manager = SessionSummaryManager()
        assert "Provide" in manager.summary_request_message or len(manager.summary_request_message) > 0

    def test_default_summaries_updated_false(self):
        manager = SessionSummaryManager()
        assert manager.summaries_updated is False

    def test_model_token_thresholds_populated(self):
        assert "claude-sonnet-4" in MODEL_TOKEN_THRESHOLDS
        assert "gpt-4o" in MODEL_TOKEN_THRESHOLDS
        assert "gemini-3-flash" in MODEL_TOKEN_THRESHOLDS

    def test_default_token_threshold_value(self):
        assert DEFAULT_TOKEN_THRESHOLD == 150_000


# ---------------------------------------------------------------------------
# NoOpSessionStore tests
# ---------------------------------------------------------------------------


class TestNoOpSessionStore:
    """Tests for NoOpSessionStore - the no-operation session store."""

    @pytest.mark.asyncio
    async def test_get_by_run_id_returns_none(self):
        store = NoOpSessionStore()
        result = await store.get_by_run_id(session_id="s1", run_id="r1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_create_run_task_returns_task(self, monkeypatch):
        from types import SimpleNamespace
        from ii_agent.engine.runtime.agent_sessions import base as base_module

        # Patch AgentRunTask to avoid SQLAlchemy mapper initialization during unit test
        FakeTask = SimpleNamespace
        monkeypatch.setattr(base_module, "AgentRunTask", FakeTask)

        store = NoOpSessionStore()
        task = await store.get_or_create_run_task(
            session_id="s1",
            run_id="r1",
        )
        assert task is not None
        # Verify session_id attribute was set
        assert task.session_id == "s1"

    @pytest.mark.asyncio
    async def test_get_or_create_run_task_version_zero(self, monkeypatch):
        from types import SimpleNamespace
        from ii_agent.engine.runtime.agent_sessions import base as base_module

        FakeTask = SimpleNamespace
        monkeypatch.setattr(base_module, "AgentRunTask", FakeTask)

        store = NoOpSessionStore()
        task = await store.get_or_create_run_task(session_id="s1", run_id="r1")
        assert task.version == 0

    @pytest.mark.asyncio
    async def test_update_run_status_returns_true(self):
        store = NoOpSessionStore()
        result = await store.update_run_status(
            run_id="r1",
            status=RunStatus.COMPLETED,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_run_task_returns_none(self):
        store = NoOpSessionStore()
        result = await store.get_run_task("r1")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_run_does_nothing(self):
        store = NoOpSessionStore()
        from types import SimpleNamespace

        run = SimpleNamespace(run_id="r1")
        # Should not raise
        await store.save_run(run)

    @pytest.mark.asyncio
    async def test_get_history_messages_returns_empty(self):
        store = NoOpSessionStore()
        result = await store.get_history_messages("s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_session_messages_returns_empty(self):
        store = NoOpSessionStore()
        result = await store.get_session_messages("s1")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_last_run_returns_none(self):
        store = NoOpSessionStore()
        result = await store.get_last_run("s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_returns_agent_session(self):
        store = NoOpSessionStore()
        session = await store.get_session("sess-1", "user-1")
        assert isinstance(session, AgentSession)
        assert session.session_id == "sess-1"
        assert session.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_delete_session_returns_true(self):
        store = NoOpSessionStore()
        result = await store.delete_session("s1")
        assert result is True
