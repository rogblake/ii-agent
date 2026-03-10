"""Unit tests for realtime/socket/schemas.py - all Pydantic schema models."""

import uuid

import pytest
from pydantic import ValidationError

from ii_agent.agent.types import AgentType
from ii_agent.agent.socket.schemas import (
    EditQueryContent,
    EnhancePromptContent,
    EventInfo,
    EventResponse,
    FileInfo,
    GETSettingsModel,
    InitAgentContent,
    QueryCommandContent,
    QueryContentInternal,
    QueryContentRequest,
    QueryToolResultInternal,
    ReviewResultContent,
    SessionInfo,
    SessionResponse,
    StartForkContent,
    UploadRequest,
    WebSocketMessage,
)


# ---------------------------------------------------------------------------
# WebSocketMessage tests
# ---------------------------------------------------------------------------


class TestWebSocketMessage:
    """Tests for WebSocketMessage schema."""

    def test_basic_construction(self):
        msg = WebSocketMessage(type="query")
        assert msg.type == "query"
        assert msg.content == {}

    def test_construction_with_content(self):
        msg = WebSocketMessage(type="init", content={"key": "value"})
        assert msg.content["key"] == "value"

    def test_default_content_is_empty_dict(self):
        msg = WebSocketMessage(type="ping")
        assert isinstance(msg.content, dict)
        assert len(msg.content) == 0

    def test_type_required(self):
        with pytest.raises(ValidationError):
            WebSocketMessage()

    def test_content_accepts_nested_dict(self):
        msg = WebSocketMessage(type="data", content={"nested": {"a": 1}})
        assert msg.content["nested"]["a"] == 1


# ---------------------------------------------------------------------------
# FileInfo tests
# ---------------------------------------------------------------------------


class TestFileInfo:
    """Tests for FileInfo schema."""

    def test_basic_construction(self):
        fi = FileInfo(path="/workspace/file.txt", content="file content here")
        assert fi.path == "/workspace/file.txt"
        assert fi.content == "file content here"

    def test_path_required(self):
        with pytest.raises(ValidationError):
            FileInfo(content="data")

    def test_content_required(self):
        with pytest.raises(ValidationError):
            FileInfo(path="/tmp/file.txt")


# ---------------------------------------------------------------------------
# UploadRequest tests
# ---------------------------------------------------------------------------


class TestUploadRequest:
    """Tests for UploadRequest schema."""

    def test_basic_construction(self):
        req = UploadRequest(
            session_id="sess-123",
            file=FileInfo(path="/tmp/file.py", content="print('hello')"),
        )
        assert req.session_id == "sess-123"
        assert req.file.path == "/tmp/file.py"

    def test_session_id_required(self):
        with pytest.raises(ValidationError):
            UploadRequest(file=FileInfo(path="/tmp/f.txt", content="data"))

    def test_file_required(self):
        with pytest.raises(ValidationError):
            UploadRequest(session_id="sess-1")


# ---------------------------------------------------------------------------
# SessionInfo tests
# ---------------------------------------------------------------------------


class TestSessionInfo:
    """Tests for SessionInfo schema."""

    def test_basic_construction(self):
        si = SessionInfo(id="sess-abc", created_at="2024-01-01T00:00:00Z")
        assert si.id == "sess-abc"
        assert si.created_at == "2024-01-01T00:00:00Z"

    def test_default_name_empty(self):
        si = SessionInfo(id="sess-abc", created_at="2024-01-01T00:00:00Z")
        assert si.name == ""

    def test_name_can_be_set(self):
        si = SessionInfo(id="sess-abc", created_at="now", name="My Session")
        assert si.name == "My Session"

    def test_id_required(self):
        with pytest.raises(ValidationError):
            SessionInfo(created_at="now")

    def test_created_at_required(self):
        with pytest.raises(ValidationError):
            SessionInfo(id="sess-abc")


# ---------------------------------------------------------------------------
# SessionResponse tests
# ---------------------------------------------------------------------------


class TestSessionResponse:
    """Tests for SessionResponse schema."""

    def test_basic_construction(self):
        sessions = [
            SessionInfo(id="s1", created_at="2024-01-01T00:00:00Z", name="A"),
            SessionInfo(id="s2", created_at="2024-01-02T00:00:00Z"),
        ]
        resp = SessionResponse(sessions=sessions)
        assert len(resp.sessions) == 2

    def test_empty_sessions_list(self):
        resp = SessionResponse(sessions=[])
        assert resp.sessions == []

    def test_sessions_required(self):
        with pytest.raises(ValidationError):
            SessionResponse()


# ---------------------------------------------------------------------------
# EventInfo tests
# ---------------------------------------------------------------------------


class TestEventInfo:
    """Tests for EventInfo schema."""

    def test_basic_construction(self):
        run_id = uuid.uuid4()
        ei = EventInfo(
            id="ev-1",
            session_id="sess-1",
            created_at="2024-01-01T00:00:00Z",
            type="message",
            content={"text": "hello"},
            workspace_dir="/workspace",
            run_id=run_id,
        )
        assert ei.id == "ev-1"
        assert ei.run_id == run_id

    def test_run_id_can_be_none(self):
        ei = EventInfo(
            id="ev-2",
            session_id="sess-1",
            created_at="2024-01-01T00:00:00Z",
            type="status",
            content={},
            workspace_dir="/workspace",
            run_id=None,
        )
        assert ei.run_id is None

    def test_all_required_fields(self):
        with pytest.raises(ValidationError):
            EventInfo(id="ev-3")

    def test_content_is_dict(self):
        ei = EventInfo(
            id="ev-4",
            session_id="s1",
            created_at="now",
            type="t",
            content={"key": "val", "num": 42},
            workspace_dir="/ws",
            run_id=None,
        )
        assert ei.content["key"] == "val"
        assert ei.content["num"] == 42


# ---------------------------------------------------------------------------
# EventResponse tests
# ---------------------------------------------------------------------------


class TestEventResponse:
    """Tests for EventResponse schema."""

    def test_basic_construction(self):
        resp = EventResponse(events=[])
        assert resp.events == []
        assert resp.run_status is None

    def test_with_run_status(self):
        resp = EventResponse(events=[], run_status="running")
        assert resp.run_status == "running"

    def test_events_required(self):
        with pytest.raises(ValidationError):
            EventResponse()


# ---------------------------------------------------------------------------
# QueryContentRequest tests
# ---------------------------------------------------------------------------


class TestQueryContentRequest:
    """Tests for QueryContentRequest schema."""

    def test_defaults(self):
        req = QueryContentRequest()
        assert req.text == ""
        assert req.resume is False
        assert req.file_ids == []

    def test_with_text(self):
        req = QueryContentRequest(text="Hello agent")
        assert req.text == "Hello agent"

    def test_with_resume(self):
        req = QueryContentRequest(resume=True)
        assert req.resume is True

    def test_with_file_ids(self):
        req = QueryContentRequest(file_ids=["id1", "id2"])
        assert req.file_ids == ["id1", "id2"]


# ---------------------------------------------------------------------------
# QueryContentInternal tests
# ---------------------------------------------------------------------------


class TestQueryContentInternal:
    """Tests for QueryContentInternal schema."""

    def test_defaults(self):
        qi = QueryContentInternal()
        assert qi.text == ""
        assert qi.resume is False
        assert qi.file_upload_paths == []
        assert qi.images_data == []

    def test_with_images_data(self):
        qi = QueryContentInternal(
            images_data=[{"content_type": "image/png", "url": "https://example.com/img.png"}]
        )
        assert len(qi.images_data) == 1
        assert qi.images_data[0]["content_type"] == "image/png"

    def test_with_file_upload_paths(self):
        qi = QueryContentInternal(file_upload_paths=["/tmp/file.txt"])
        assert qi.file_upload_paths == ["/tmp/file.txt"]


# ---------------------------------------------------------------------------
# QueryToolResultInternal tests
# ---------------------------------------------------------------------------


class TestQueryToolResultInternal:
    """Tests for QueryToolResultInternal schema."""

    def test_basic_construction(self):
        result = QueryToolResultInternal(
            tool_call_id="tc-1",
            tool_name="bash",
        )
        assert result.tool_call_id == "tc-1"
        assert result.tool_name == "bash"
        assert result.tool_input == {}
        assert result.is_error is False
        assert result.is_interrupted is False

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            QueryToolResultInternal()

    def test_with_error(self):
        result = QueryToolResultInternal(
            tool_call_id="tc-2",
            tool_name="read_file",
            is_error=True,
        )
        assert result.is_error is True

    def test_with_content(self):
        result = QueryToolResultInternal(
            tool_call_id="tc-3",
            tool_name="write",
            tool_input={"path": "/tmp/f.txt", "content": "data"},
            llm_content="file written",
            user_display_content="Done",
        )
        assert result.tool_input["path"] == "/tmp/f.txt"
        assert result.llm_content == "file written"
        assert result.user_display_content == "Done"


# ---------------------------------------------------------------------------
# InitAgentContent tests
# ---------------------------------------------------------------------------


class TestInitAgentContent:
    """Tests for InitAgentContent schema."""

    def test_defaults(self):
        iac = InitAgentContent()
        assert iac.model_id is None
        assert iac.tool_args == {}
        assert iac.source is None
        assert iac.thinking_tokens == 0
        assert iac.agent_type == AgentType.GENERAL
        assert iac.metadata is None

    def test_with_model_id(self):
        iac = InitAgentContent(model_id="claude-3-5-sonnet")
        assert iac.model_id == "claude-3-5-sonnet"

    def test_with_agent_type(self):
        iac = InitAgentContent(agent_type=AgentType.SLIDE)
        assert iac.agent_type == AgentType.SLIDE

    def test_with_source(self):
        iac = InitAgentContent(source="user")
        assert iac.source == "user"

    def test_with_thinking_tokens(self):
        iac = InitAgentContent(thinking_tokens=1024)
        assert iac.thinking_tokens == 1024

    def test_with_metadata(self):
        iac = InitAgentContent(metadata={"template_id": "t-1"})
        assert iac.metadata["template_id"] == "t-1"


# ---------------------------------------------------------------------------
# QueryCommandContent tests
# ---------------------------------------------------------------------------


class TestQueryCommandContent:
    """Tests for QueryCommandContent schema."""

    def test_basic_construction(self):
        qcc = QueryCommandContent(
            model_id="gpt-4o",
            provider="openai",
            agent_type=AgentType.GENERAL,
        )
        assert qcc.model_id == "gpt-4o"
        assert qcc.provider == "openai"
        assert qcc.agent_type == AgentType.GENERAL

    def test_defaults(self):
        qcc = QueryCommandContent(
            model_id=None,
            provider=None,
            agent_type=AgentType.GENERAL,
        )
        assert qcc.text == ""
        assert qcc.resume is False
        assert qcc.files == []
        assert qcc.thinking_tokens == 0
        assert qcc.build_mode == "build"

    def test_with_text(self):
        qcc = QueryCommandContent(
            model_id=None,
            provider=None,
            agent_type=AgentType.GENERAL,
            text="Build me a website",
        )
        assert qcc.text == "Build me a website"

    def test_with_milestone_ids(self):
        qcc = QueryCommandContent(
            model_id=None,
            provider=None,
            agent_type=AgentType.GENERAL,
            milestone_ids=["m1", "m2"],
        )
        assert qcc.milestone_ids == ["m1", "m2"]

    def test_with_github_repository(self):
        qcc = QueryCommandContent(
            model_id=None,
            provider=None,
            agent_type=AgentType.GENERAL,
            github_repository={"owner": "user", "name": "repo", "full_name": "user/repo"},
        )
        assert qcc.github_repository["owner"] == "user"

    def test_extra_fields_allowed(self):
        qcc = QueryCommandContent(
            model_id=None,
            provider=None,
            agent_type=AgentType.GENERAL,
            custom_extra="value",
        )
        # Config has extra="allow"
        assert qcc.custom_extra == "value"  # type: ignore


# ---------------------------------------------------------------------------
# EnhancePromptContent tests
# ---------------------------------------------------------------------------


class TestEnhancePromptContent:
    """Tests for EnhancePromptContent schema."""

    def test_defaults(self):
        epc = EnhancePromptContent()
        assert epc.text == ""
        assert epc.files == []

    def test_with_text_and_files(self):
        epc = EnhancePromptContent(text="make it better", files=["file1.txt"])
        assert epc.text == "make it better"
        assert epc.files == ["file1.txt"]


# ---------------------------------------------------------------------------
# EditQueryContent tests
# ---------------------------------------------------------------------------


class TestEditQueryContent:
    """Tests for EditQueryContent schema."""

    def test_defaults(self):
        eqc = EditQueryContent()
        assert eqc.text == ""
        assert eqc.resume is False
        assert eqc.files == []

    def test_with_values(self):
        eqc = EditQueryContent(text="change this", resume=True, files=["f.py"])
        assert eqc.text == "change this"
        assert eqc.resume is True
        assert eqc.files == ["f.py"]


# ---------------------------------------------------------------------------
# ReviewResultContent tests
# ---------------------------------------------------------------------------


class TestReviewResultContent:
    """Tests for ReviewResultContent schema."""

    def test_default(self):
        rrc = ReviewResultContent()
        assert rrc.user_input == ""

    def test_with_input(self):
        rrc = ReviewResultContent(user_input="looks good")
        assert rrc.user_input == "looks good"


# ---------------------------------------------------------------------------
# StartForkContent tests
# ---------------------------------------------------------------------------


class TestStartForkContent:
    """Tests for StartForkContent schema."""

    def test_defaults(self):
        sfc = StartForkContent()
        assert sfc.model_id is None
        assert sfc.source == "system"
        assert sfc.agent_type is None
        assert sfc.tool_args == {}
        assert sfc.thinking_tokens == 0
        assert sfc.metadata is None

    def test_with_agent_type(self):
        sfc = StartForkContent(agent_type="website_build")
        assert sfc.agent_type == "website_build"

    def test_with_model_id(self):
        sfc = StartForkContent(model_id="claude-3-5-sonnet")
        assert sfc.model_id == "claude-3-5-sonnet"

    def test_with_source_user(self):
        sfc = StartForkContent(source="user")
        assert sfc.source == "user"


# ---------------------------------------------------------------------------
# GETSettingsModel tests
# ---------------------------------------------------------------------------


class TestGETSettingsModel:
    """Tests for GETSettingsModel schema."""

    def test_basic_construction(self):
        model = GETSettingsModel(
            llm_api_key_set=True,
            search_api_key_set=False,
        )
        assert model.llm_api_key_set is True
        assert model.search_api_key_set is False

    def test_defaults_llm_configs(self):
        model = GETSettingsModel(
            llm_api_key_set=False,
            search_api_key_set=False,
        )
        assert model.llm_configs == {}

    def test_required_flags(self):
        with pytest.raises(ValidationError):
            GETSettingsModel()

    def test_both_flags_true(self):
        model = GETSettingsModel(
            llm_api_key_set=True,
            search_api_key_set=True,
        )
        assert model.llm_api_key_set is True
        assert model.search_api_key_set is True
