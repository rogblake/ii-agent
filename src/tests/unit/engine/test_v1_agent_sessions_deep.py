"""Deep unit tests for ii_agent.agents.sessions.agent (AgentSession)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from ii_agent.agents.sessions.agent import AgentSession


# ---------------------------------------------------------------------------
# AgentSession.to_dict
# ---------------------------------------------------------------------------


class TestAgentSessionToDict:
    def test_minimal_session_to_dict(self):
        session = AgentSession(session_id="s-1", user_id="u-1")
        result = session.to_dict()
        assert result["session_id"] == "s-1"
        assert result["user_id"] == "u-1"

    def test_session_with_runs_to_dict(self):
        run1 = MagicMock()
        run1.to_dict.return_value = {"id": "run-1"}
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            runs=[run1],
        )
        result = session.to_dict()
        assert result["runs"] == [{"id": "run-1"}]

    def test_session_with_no_runs_yields_none(self):
        session = AgentSession(session_id="s-1", user_id="u-1", runs=None)
        result = session.to_dict()
        assert result["runs"] is None

    def test_session_with_summary_to_dict(self):
        summary = MagicMock()
        summary.to_dict.return_value = {"total": 5}
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            summary=summary,
        )
        result = session.to_dict()
        assert result["summary"] == {"total": 5}

    def test_session_with_no_summary_yields_none(self):
        session = AgentSession(session_id="s-1", user_id="u-1", summary=None)
        result = session.to_dict()
        assert result["summary"] is None

    def test_session_with_metadata_to_dict(self):
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            metadata={"key": "value"},
        )
        result = session.to_dict()
        assert result["metadata"] == {"key": "value"}

    def test_session_with_agent_data_to_dict(self):
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            agent_data={"model": "gpt-4"},
        )
        result = session.to_dict()
        assert result["agent_data"] == {"model": "gpt-4"}

    def test_session_with_session_data_to_dict(self):
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            session_data={"history": []},
        )
        result = session.to_dict()
        assert result["session_data"] == {"history": []}

    def test_session_timestamps_included(self):
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            created_at=1000000,
            updated_at=2000000,
        )
        result = session.to_dict()
        assert result["created_at"] == 1000000
        assert result["updated_at"] == 2000000

    def test_session_agent_id_included(self):
        session = AgentSession(
            session_id="s-1",
            user_id="u-1",
            agent_id="agent-42",
        )
        result = session.to_dict()
        assert result["agent_id"] == "agent-42"


# ---------------------------------------------------------------------------
# AgentSession.from_dict
# ---------------------------------------------------------------------------


class TestAgentSessionFromDict:
    def test_returns_none_when_data_is_none(self):
        result = AgentSession.from_dict(None)
        assert result is None

    def test_returns_none_when_session_id_missing(self):
        result = AgentSession.from_dict({"user_id": "u-1"})
        assert result is None

    def test_returns_none_when_user_id_missing(self):
        result = AgentSession.from_dict({"session_id": "s-1"})
        assert result is None

    def test_creates_session_with_minimal_data(self):
        data = {"session_id": "s-1", "user_id": "u-1"}
        session = AgentSession.from_dict(data)
        assert session is not None
        assert session.session_id == "s-1"
        assert session.user_id == "u-1"

    def test_deserializes_run_messages_as_list_of_run_outputs(self):
        run_data = {"id": "r-1", "status": "completed"}
        data = {
            "session_id": "s-1",
            "user_id": "u-1",
            "run_messages": [run_data],
        }
        with patch("ii_agent.agents.sessions.agent.RunOutput.from_dict") as mock_from_dict:
            mock_from_dict.return_value = MagicMock()
            session = AgentSession.from_dict(data)
        assert session is not None
        assert len(session.runs) == 1

    def test_skips_non_dict_runs_in_run_messages(self):
        from ii_agent.agents.runs.agent import RunOutput

        mock_run = MagicMock(spec=RunOutput)
        data = {
            "session_id": "s-1",
            "user_id": "u-1",
            "run_messages": [mock_run],
        }
        session = AgentSession.from_dict(data)
        assert session is not None
        # RunOutput instances should be included as-is
        assert len(session.runs) == 1
        assert session.runs[0] is mock_run

    def test_deserializes_summary_from_dict(self):
        data = {
            "session_id": "s-1",
            "user_id": "u-1",
            "summary": {"total_runs": 3},
        }
        with patch("ii_agent.agents.sessions.agent.AgentSummary.from_dict") as mock_from_dict:
            mock_from_dict.return_value = MagicMock()
            session = AgentSession.from_dict(data)
        assert session is not None
        mock_from_dict.assert_called_once_with({"total_runs": 3})

    def test_summary_not_deserialized_if_not_dict(self):
        data = {
            "session_id": "s-1",
            "user_id": "u-1",
            "summary": None,
        }
        session = AgentSession.from_dict(data)
        assert session is not None
        assert session.summary is None

    def test_includes_optional_fields(self):
        data = {
            "session_id": "s-1",
            "user_id": "u-1",
            "agent_id": "agent-42",
            "agent_data": {"model": "gpt-4"},
            "session_data": {"key": "value"},
            "metadata": {"extra": "info"},
        }
        session = AgentSession.from_dict(data)
        assert session is not None
        assert session.agent_id == "agent-42"
        assert session.agent_data == {"model": "gpt-4"}
        assert session.session_data == {"key": "value"}
        assert session.metadata == {"extra": "info"}

    def test_no_run_messages_key_yields_empty_runs(self):
        data = {"session_id": "s-1", "user_id": "u-1"}
        session = AgentSession.from_dict(data)
        assert session is not None
        # No run_messages key → serialized_runs = []
        assert session.runs == []

    def test_empty_run_messages_yields_empty_runs(self):
        data = {
            "session_id": "s-1",
            "user_id": "u-1",
            "run_messages": [],
        }
        session = AgentSession.from_dict(data)
        assert session is not None
        assert session.runs == []
