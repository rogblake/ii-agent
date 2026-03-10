"""Unit tests for skill.py, dev/init_tool.py, slide_system/hook_utils.py, and message_user.py - r4.

Covers:
- SkillTool.__init__ and execute (various cases)
- SendUserFile.execute (valid input, error cases)
- SendUserFile.on_tool_end (attachment processing)
- _determine_file_type, _is_remote_url, _guess_name_from_path, _generate_storage_path
- FullStackInitTool.execute (no database, database false, no session_id)
- FullStackInitTool.on_tool_end (missing project name, success)
- process_slide_content (various tool_name scenarios)
- GitHub skill: sanitize_skill_name, GitHubDownloadService.parse_url
"""
from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# SkillTool
# ---------------------------------------------------------------------------

class TestSkillToolInit:
    """Test SkillTool.__init__."""

    def test_init_stores_description(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        tool = SkillTool(description="Available skills: pdf, xlsx")
        assert tool.description == "Available skills: pdf, xlsx"

    def test_init_empty_registry_by_default(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        tool = SkillTool(description="desc")
        assert tool._skills_registry == {}

    def test_init_with_registry(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        skill_mock = MagicMock()
        tool = SkillTool(description="desc", skills_registry={"pdf": skill_mock})
        assert "pdf" in tool._skills_registry

    def test_tool_name_is_skill(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        tool = SkillTool(description="desc")
        assert tool.name == "Skill"

    def test_input_schema_has_skill_key(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        tool = SkillTool(description="desc")
        assert "skill" in tool.input_schema["properties"]


class TestSkillToolExecute:
    """Test SkillTool.execute."""

    def _make_tool(self, skills=None):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        return SkillTool(description="desc", skills_registry=skills or {})

    @pytest.mark.asyncio
    async def test_no_skill_name_returns_error(self):
        tool = self._make_tool()
        result = await tool.execute({"skill": ""})
        assert result.is_error is True
        assert "No skill name" in result.llm_content

    @pytest.mark.asyncio
    async def test_skill_not_in_registry_returns_error(self):
        tool = self._make_tool()
        result = await tool.execute({"skill": "unknown_skill"})
        assert result.is_error is True
        assert "not found" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_agent_not_initialized_returns_error(self):
        skill_mock = MagicMock()
        skill_mock.storage_uri = "skills/pdf"
        skill_mock.source = "builtin"

        tool = self._make_tool(skills={"pdf": skill_mock})
        tool._agent = None  # No agent set

        result = await tool.execute({"skill": "pdf"})
        assert result.is_error is True
        assert "Agent not initialized" in result.llm_content

    @pytest.mark.asyncio
    async def test_sandbox_not_initialized_returns_error(self):
        skill_mock = MagicMock()
        skill_mock.storage_uri = "skills/pdf"
        skill_mock.source = "builtin"

        tool = self._make_tool(skills={"pdf": skill_mock})
        agent_mock = MagicMock()
        agent_mock.sandbox = None
        tool._agent = agent_mock

        result = await tool.execute({"skill": "pdf"})
        assert result.is_error is True
        assert "Sandbox not initialized" in result.llm_content

    @pytest.mark.asyncio
    async def test_skill_file_not_found_returns_error(self):
        skill_mock = MagicMock()
        skill_mock.storage_uri = "skills/pdf"
        skill_mock.source = "builtin"

        tool = self._make_tool(skills={"pdf": skill_mock})
        agent_mock = MagicMock()
        agent_mock.sandbox = MagicMock()
        tool._agent = agent_mock

        with patch("ii_agent.agent.runtime.tools.skill.skill_exists", AsyncMock(return_value=False)):
            result = await tool.execute({"skill": "pdf"})

        assert result.is_error is True
        assert "not found" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_successful_skill_activation(self):
        skill_mock = MagicMock()
        skill_mock.storage_uri = "skills/pdf"
        skill_mock.source = "builtin"
        skill_mock.skill_md_content = "# PDF Skill\n\nUse this skill to process PDFs."

        tool = self._make_tool(skills={"pdf": skill_mock})
        agent_mock = MagicMock()
        agent_mock.sandbox = MagicMock()
        tool._agent = agent_mock

        with (
            patch("ii_agent.agent.runtime.tools.skill.skill_exists", AsyncMock(return_value=True)),
            patch(
                "ii_agent.agent.runtime.tools.skill.copy_skill_to_sandbox",
                AsyncMock(return_value="/workspace/.skills/pdf"),
            ),
        ):
            result = await tool.execute({"skill": "pdf"})

        assert result.is_error is not True
        assert "pdf" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_exception_during_copy_returns_error(self):
        skill_mock = MagicMock()
        skill_mock.storage_uri = "skills/pdf"
        skill_mock.source = "builtin"

        tool = self._make_tool(skills={"pdf": skill_mock})
        agent_mock = MagicMock()
        agent_mock.sandbox = MagicMock()
        tool._agent = agent_mock

        with (
            patch("ii_agent.agent.runtime.tools.skill.skill_exists", AsyncMock(return_value=True)),
            patch(
                "ii_agent.agent.runtime.tools.skill.copy_skill_to_sandbox",
                AsyncMock(side_effect=RuntimeError("Copy failed")),
            ),
        ):
            result = await tool.execute({"skill": "pdf"})

        assert result.is_error is True
        assert "Copy failed" in result.llm_content

    @pytest.mark.asyncio
    async def test_on_tool_start_stores_agent(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        tool = SkillTool(description="desc")
        agent_mock = MagicMock()
        agent_mock.sandbox = None
        fc_mock = MagicMock()

        with patch.object(type(tool).__bases__[0], "on_tool_start", AsyncMock()):
            await tool.on_tool_start(agent_mock, fc_mock)

        assert tool._agent is agent_mock

    def test_available_skills_listed_in_error(self):
        from ii_agent.agent.runtime.tools.skill import SkillTool

        skill1 = MagicMock()
        skill2 = MagicMock()
        tool = SkillTool(description="desc", skills_registry={"pdf": skill1, "xlsx": skill2})

        async def run():
            return await tool.execute({"skill": "nonexistent"})

        import asyncio
        result = asyncio.get_event_loop().run_until_complete(run())
        assert "pdf" in result.llm_content or "xlsx" in result.llm_content


# ---------------------------------------------------------------------------
# SendUserFile (message_user.py)
# ---------------------------------------------------------------------------

class TestSendUserFileExecute:
    """Test SendUserFile.execute."""

    def _make_tool(self):
        from ii_agent.agent.runtime.tools.agent.message_user import SendUserFile

        return SendUserFile()

    @pytest.mark.asyncio
    async def test_basic_execute_with_message_and_attachments(self):
        tool = self._make_tool()
        result = await tool.execute({"message": "Here are your files", "attachments": ["/tmp/file.pdf"]})
        assert result.is_error is not True
        assert result.llm_content is not None

    @pytest.mark.asyncio
    async def test_empty_attachments_allowed(self):
        tool = self._make_tool()
        result = await tool.execute({"message": "No files", "attachments": []})
        assert result.is_error is not True

    @pytest.mark.asyncio
    async def test_non_string_message_returns_error(self):
        tool = self._make_tool()
        result = await tool.execute({"message": 123, "attachments": []})
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_non_list_attachments_returns_error(self):
        tool = self._make_tool()
        result = await tool.execute({"message": "test", "attachments": "not_a_list"})
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_none_attachments_treated_as_empty(self):
        tool = self._make_tool()
        result = await tool.execute({"message": "test", "attachments": None})
        assert result.is_error is not True

    @pytest.mark.asyncio
    async def test_missing_message_defaults_to_empty_string(self):
        tool = self._make_tool()
        result = await tool.execute({"attachments": ["/tmp/file.txt"]})
        assert result.is_error is not True

    @pytest.mark.asyncio
    async def test_result_payload_structure(self):
        import json
        tool = self._make_tool()
        result = await tool.execute({"message": "Hello", "attachments": ["/tmp/a.pdf"]})
        # llm_content should be JSON with tool_name and action
        payload = json.loads(result.llm_content)
        assert payload["tool_name"] == "message"
        assert "action" in payload
        assert payload["action"]["text"] == "Hello"


# ---------------------------------------------------------------------------
# _determine_file_type, _is_remote_url, _guess_name_from_path
# ---------------------------------------------------------------------------

class TestMessageUserHelpers:
    """Test helper functions in message_user.py."""

    def test_determine_file_type_code(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _determine_file_type

        assert _determine_file_type("main.py") == "code"
        assert _determine_file_type("app.ts") == "code"
        assert _determine_file_type("script.js") == "code"
        assert _determine_file_type("styles.css") == "code"
        assert _determine_file_type("config.yaml") == "code"
        assert _determine_file_type("README.md") == "code"

    def test_determine_file_type_spreadsheet(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _determine_file_type

        assert _determine_file_type("data.xlsx") == "xlsx"
        assert _determine_file_type("data.csv") == "xlsx"
        assert _determine_file_type("data.xls") == "xlsx"

    def test_determine_file_type_archive(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _determine_file_type

        assert _determine_file_type("archive.zip") == "archive"
        assert _determine_file_type("backup.tar.gz") == "archive"
        assert _determine_file_type("data.rar") == "archive"

    def test_determine_file_type_document(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _determine_file_type

        assert _determine_file_type("report.pdf") == "documents"
        assert _determine_file_type("letter.docx") == "documents"
        assert _determine_file_type("notes.txt") == "documents"

    def test_determine_file_type_unknown_defaults_to_documents(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _determine_file_type

        assert _determine_file_type("unknown.xyz") == "documents"

    def test_is_remote_url_http(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _is_remote_url

        assert _is_remote_url("http://example.com/file.pdf") is True

    def test_is_remote_url_https(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _is_remote_url

        assert _is_remote_url("https://secure.example.com/file.pdf") is True

    def test_is_remote_url_local_path(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _is_remote_url

        assert _is_remote_url("/local/path/file.pdf") is False

    def test_is_remote_url_relative_path(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _is_remote_url

        assert _is_remote_url("relative/path/file.pdf") is False

    def test_guess_name_from_path_url(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _guess_name_from_path

        result = _guess_name_from_path("http://example.com/path/to/file.pdf")
        assert result == "file.pdf"

    def test_guess_name_from_path_local(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _guess_name_from_path

        result = _guess_name_from_path("/some/local/path/file.txt")
        assert result == "file.txt"

    def test_guess_name_from_path_empty_returns_attachment(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _guess_name_from_path

        # Empty path or root returns fallback
        result = _guess_name_from_path("")
        assert isinstance(result, str)

    def test_generate_storage_path_includes_session(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _generate_storage_path

        result = _generate_storage_path("file.pdf", "session-123")
        assert "session-123" in result
        assert "file.pdf" in result
        assert result.startswith("sessions/")

    def test_generate_storage_path_no_session_uses_unknown(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _generate_storage_path

        result = _generate_storage_path("file.pdf", None)
        assert "unknown-session" in result


# ---------------------------------------------------------------------------
# _process_attachment
# ---------------------------------------------------------------------------

class TestProcessAttachment:
    """Test _process_attachment helper."""

    @pytest.mark.asyncio
    async def test_dict_with_url_returns_meta(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        result = await _process_attachment(
            {"name": "file.pdf", "url": "http://example.com/file.pdf"},
            session_id="s1",
            sandbox=None,
            storage=storage,
        )
        assert result is not None
        assert result["url"] == "http://example.com/file.pdf"
        assert result["name"] == "file.pdf"

    @pytest.mark.asyncio
    async def test_dict_without_url_returns_none(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        result = await _process_attachment(
            {"name": "file.pdf"},
            session_id="s1",
            sandbox=None,
            storage=storage,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_remote_url_string_returns_meta(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        result = await _process_attachment(
            "http://example.com/image.png",
            session_id="s1",
            sandbox=None,
            storage=storage,
        )
        assert result is not None
        assert result["url"] == "http://example.com/image.png"
        assert result["name"] == "image.png"

    @pytest.mark.asyncio
    async def test_non_string_non_dict_returns_none(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        result = await _process_attachment(
            12345,
            session_id="s1",
            sandbox=None,
            storage=storage,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_local_path_without_sandbox_returns_none(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        result = await _process_attachment(
            "/local/path/file.pdf",
            session_id="s1",
            sandbox=None,
            storage=storage,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_local_path_with_sandbox_success(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        storage.get_upload_signed_url = MagicMock(return_value="http://upload.example.com/url")
        storage.get_permanent_url = MagicMock(return_value="http://storage.example.com/file.pdf")

        fake_content = b"file content bytes"

        sandbox = MagicMock()
        sandbox.download_file_stream = MagicMock(return_value=iter([fake_content]))

        mock_http_response = MagicMock()
        mock_http_response.is_success = True

        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_http_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _process_attachment(
                "/local/path/file.pdf",
                session_id="sess-1",
                sandbox=sandbox,
                storage=storage,
            )

        assert result is not None
        assert result["name"] == "file.pdf"

    @pytest.mark.asyncio
    async def test_local_path_upload_failure_returns_none(self):
        from ii_agent.agent.runtime.tools.agent.message_user import _process_attachment

        storage = MagicMock()
        storage.get_upload_signed_url = MagicMock(return_value="http://upload.example.com/url")

        sandbox = MagicMock()
        sandbox.download_file_stream = MagicMock(return_value=iter([b"content"]))

        mock_http_response = MagicMock()
        mock_http_response.is_success = False
        mock_http_response.status_code = 403
        mock_http_response.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=mock_http_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _process_attachment(
                "/local/path/file.pdf",
                session_id="sess-1",
                sandbox=sandbox,
                storage=storage,
            )

        assert result is None


# ---------------------------------------------------------------------------
# FullStackInitTool.execute (dev/init_tool.py)
# ---------------------------------------------------------------------------

class TestFullStackInitToolExecute:
    """Test FullStackInitTool.execute."""

    def _make_tool(self):
        from ii_agent.agent.runtime.tools.dev.init_tool import FullStackInitTool

        tool = FullStackInitTool.__new__(FullStackInitTool)
        tool.name = "fullstack_project_init"
        tool.display_name = "Initialize application template"
        tool.description = "Init tool"
        tool.input_schema = {}
        tool.read_only = False
        tool.mcp_client = None
        tool._session_id = None
        tool._user_id = None
        tool.dependencies = MagicMock()
        tool.dependencies.project_service = MagicMock()
        return tool

    @pytest.mark.asyncio
    async def test_execute_without_database_calls_execute(self):
        tool = self._make_tool()
        tool._execute = AsyncMock(return_value=MagicMock(is_error=False, llm_content="ok"))

        result = await tool.execute({"project_name": "myapp", "framework": "nextjs-shadcn", "database": False})
        tool._execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_without_database_key_calls_execute(self):
        tool = self._make_tool()
        tool._execute = AsyncMock(return_value=MagicMock(is_error=False, llm_content="ok"))

        result = await tool.execute({"project_name": "myapp", "framework": "nextjs-shadcn"})
        tool._execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_database_no_session_returns_error(self):
        tool = self._make_tool()
        tool._session_id = None

        result = await tool.execute({"project_name": "myapp", "framework": "nextjs-shadcn", "database": True})
        assert result.is_error is True
        assert "session_id" in result.llm_content.lower() or "session" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_execute_with_database_and_session_uses_existing_db(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = self._make_tool()
        tool._session_id = "sess-1"
        tool._user_id = "user-1"
        tool._execute = AsyncMock(return_value=ToolResult(llm_content="ok", is_error=False))

        existing_db = MagicMock()
        existing_db.connection_string = "postgres://user:pass@host:5432/db"

        mock_repo = MagicMock()
        mock_repo.get_active_by_session_id = AsyncMock(return_value=existing_db)

        with (
            patch("ii_agent.agent.runtime.tools.dev.init_tool.ProjectDatabaseRepository", return_value=mock_repo),
            patch("ii_agent.agent.runtime.tools.dev.init_tool.get_db_session_local") as mock_db,
        ):
            mock_db_ctx = AsyncMock()
            mock_db_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_db_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_db_ctx

            result = await tool.execute({
                "project_name": "myapp",
                "framework": "nextjs-shadcn",
                "database": True,
            })

        tool._execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_exception_returns_error(self):
        tool = self._make_tool()
        tool._execute = AsyncMock(side_effect=RuntimeError("Unexpected error"))
        tool._session_id = None

        result = await tool.execute({"project_name": "myapp", "framework": "nextjs-shadcn", "database": False})
        assert result.is_error is True
        assert "Unexpected error" in result.llm_content

    @pytest.mark.asyncio
    async def test_on_tool_start_sets_session_and_user_id(self):
        from ii_agent.agent.runtime.tools.dev.init_tool import FullStackInitTool

        tool = self._make_tool()
        agent_mock = MagicMock()
        agent_mock.session_id = "sess-99"
        agent_mock.user_id = "user-99"
        fc_mock = MagicMock()

        with patch.object(type(tool).__bases__[0], "on_tool_start", AsyncMock()):
            await tool.on_tool_start(agent_mock, fc_mock)

        assert tool._session_id == "sess-99"
        assert tool._user_id == "user-99"


class TestFullStackInitToolOnToolEnd:
    """Test FullStackInitTool.on_tool_end."""

    def _make_tool(self):
        from ii_agent.agent.runtime.tools.dev.init_tool import FullStackInitTool
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = FullStackInitTool.__new__(FullStackInitTool)
        tool.name = "fullstack_project_init"
        tool.dependencies = MagicMock()
        tool.dependencies.project_service = MagicMock()
        return tool

    @pytest.mark.asyncio
    async def test_on_tool_end_fc_error_returns_early(self):
        tool = self._make_tool()
        fc = MagicMock()
        fc.error = "Some error"
        agent = MagicMock()
        agent.session_id = "sess-1"

        # Should not raise or call project_service
        await tool.on_tool_end(agent, fc)
        tool.dependencies.project_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_tool_end_no_session_returns_early(self):
        tool = self._make_tool()
        fc = MagicMock()
        fc.error = None
        agent = MagicMock()
        agent.session_id = None

        await tool.on_tool_end(agent, fc)

    @pytest.mark.asyncio
    async def test_on_tool_end_tool_result_is_error_returns_early(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = self._make_tool()
        fc = MagicMock()
        fc.error = None
        fc.result = ToolResult(llm_content="error", is_error=True)

        agent = MagicMock()
        agent.session_id = "sess-1"
        agent.user_id = "user-1"

        await tool.on_tool_end(agent, fc)
        # project_service should not be called
        tool.dependencies.project_service.create_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_tool_end_non_dict_display_content_returns_early(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = self._make_tool()
        fc = MagicMock()
        fc.error = None
        fc.result = ToolResult(llm_content="ok", user_display_content="string content", is_error=False)

        agent = MagicMock()
        agent.session_id = "sess-1"
        agent.user_id = "user-1"

        await tool.on_tool_end(agent, fc)

    @pytest.mark.asyncio
    async def test_on_tool_end_no_project_name_returns_early(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = self._make_tool()
        fc = MagicMock()
        fc.error = None
        fc.result = ToolResult(
            llm_content="ok",
            user_display_content={"framework": "nextjs"},
            is_error=False,
        )

        agent = MagicMock()
        agent.session_id = "sess-1"
        agent.user_id = "user-1"

        await tool.on_tool_end(agent, fc)

    @pytest.mark.asyncio
    async def test_on_tool_end_success_persists_project(self):
        from ii_agent.agent.runtime.tools.base import ToolResult

        tool = self._make_tool()
        fc = MagicMock()
        fc.error = None
        fc.result = ToolResult(
            llm_content="ok",
            user_display_content={
                "project_name": "myapp",
                "framework": "nextjs-shadcn",
                "directory": "/workspace/myapp",
                "description": "My app",
            },
            is_error=False,
        )

        project_record = MagicMock()
        project_record.id = "proj-1"
        project_record.name = "myapp"
        project_record.framework = "nextjs-shadcn"
        project_record.project_path = "/workspace/myapp"

        tool._persist_project_metadata = AsyncMock(return_value={
            "id": "proj-1",
            "name": "myapp",
            "framework": "nextjs-shadcn",
            "project_path": "/workspace/myapp",
        })

        agent = MagicMock()
        agent.session_id = "sess-1"
        agent.user_id = "user-1"

        await tool.on_tool_end(agent, fc)
        tool._persist_project_metadata.assert_called_once()


# ---------------------------------------------------------------------------
# slide_system/hook_utils.py - process_slide_content
# ---------------------------------------------------------------------------

class TestProcessSlideContent:
    """Test process_slide_content function."""

    def _make_agent_with_sandbox(self):
        agent = MagicMock()
        agent.sandbox = MagicMock()
        return agent

    @pytest.mark.asyncio
    async def test_returns_content_when_no_custom_domain(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = None

        with patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings):
            content = {"key": "value"}
            result = await process_slide_content(
                agent=MagicMock(),
                tool_name="slide_create",
                user_display_content=content,
            )

        assert result is content

    @pytest.mark.asyncio
    async def test_returns_content_when_no_sandbox(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = "custom.example.com"

        agent = MagicMock()
        agent.sandbox = None

        with patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings):
            content = {"key": "value"}
            result = await process_slide_content(
                agent=agent,
                tool_name="slide_create",
                user_display_content=content,
            )

        assert result is content

    @pytest.mark.asyncio
    async def test_returns_content_when_storage_build_fails(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = "custom.example.com"
        settings.storage.slide_assets_project_id = None
        settings.storage.file_upload_project_id = None
        settings.storage.slide_assets_bucket_name = None
        settings.storage.file_upload_bucket_name = None

        agent = self._make_agent_with_sandbox()

        with patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings):
            content = {"key": "value"}
            result = await process_slide_content(
                agent=agent,
                tool_name="slide_create",
                user_display_content=content,
            )

        assert result is content

    @pytest.mark.asyncio
    async def test_processes_slide_apply_patch(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = "custom.example.com"
        settings.storage.slide_assets_project_id = "proj"
        settings.storage.slide_assets_bucket_name = "bucket"
        settings.storage.provider = "gcs"

        agent = self._make_agent_with_sandbox()

        processed_html = "<html>processed</html>"

        mock_processor = AsyncMock()
        mock_processor.process_html_content = AsyncMock(return_value=processed_html)

        slide_content = [
            {"new_content": "<html>original</html>", "filepath": "/slides/slide1.html"}
        ]

        with (
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils._build_storage", return_value=MagicMock()),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.SlideContentProcessor", return_value=mock_processor),
        ):
            result = await process_slide_content(
                agent=agent,
                tool_name="slide_apply_patch",
                user_display_content=slide_content,
            )

        assert result[0]["new_content"] == processed_html

    @pytest.mark.asyncio
    async def test_processes_dict_with_content_key(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = "custom.example.com"
        settings.storage.slide_assets_project_id = "proj"
        settings.storage.slide_assets_bucket_name = "bucket"
        settings.storage.provider = "gcs"

        agent = self._make_agent_with_sandbox()

        processed_html = "<html>processed</html>"

        mock_processor = AsyncMock()
        mock_processor.process_html_content = AsyncMock(return_value=processed_html)

        content = {"content": "<html>original</html>", "filepath": "/slides/slide1.html"}

        with (
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils._build_storage", return_value=MagicMock()),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.SlideContentProcessor", return_value=mock_processor),
        ):
            result = await process_slide_content(
                agent=agent,
                tool_name="slide_create",
                user_display_content=content,
            )

        assert result["content"] == processed_html

    @pytest.mark.asyncio
    async def test_processes_list_with_new_content_key(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = "custom.example.com"
        settings.storage.slide_assets_project_id = "proj"
        settings.storage.slide_assets_bucket_name = "bucket"
        settings.storage.provider = "gcs"

        agent = self._make_agent_with_sandbox()

        processed_html = "<html>processed</html>"

        mock_processor = AsyncMock()
        mock_processor.process_html_content = AsyncMock(return_value=processed_html)

        slide_list = [
            {"new_content": "<html>original</html>", "filepath": "/slides/s1.html"},
            {"other": "data"},  # No new_content, should be skipped
        ]

        with (
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils._build_storage", return_value=MagicMock()),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.SlideContentProcessor", return_value=mock_processor),
        ):
            result = await process_slide_content(
                agent=agent,
                tool_name="some_tool",
                user_display_content=slide_list,
            )

        assert result[0]["new_content"] == processed_html
        # Second item without new_content should be unchanged
        assert result[1] == {"other": "data"}

    @pytest.mark.asyncio
    async def test_returns_content_unchanged_for_non_matching_format(self):
        from ii_agent.agent.runtime.tools.slide_system.hook_utils import process_slide_content

        settings = MagicMock()
        settings.storage.custom_domain = "custom.example.com"
        settings.storage.slide_assets_project_id = "proj"
        settings.storage.slide_assets_bucket_name = "bucket"
        settings.storage.provider = "gcs"

        agent = self._make_agent_with_sandbox()

        mock_processor = AsyncMock()

        with (
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.get_settings", return_value=settings),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils._build_storage", return_value=MagicMock()),
            patch("ii_agent.agent.runtime.tools.slide_system.hook_utils.SlideContentProcessor", return_value=mock_processor),
        ):
            plain_string = "just a string"
            result = await process_slide_content(
                agent=agent,
                tool_name="some_tool",
                user_display_content=plain_string,
            )

        assert result == plain_string


# ---------------------------------------------------------------------------
# GitHub skill: sanitize_skill_name and GitHubDownloadService.parse_url
# ---------------------------------------------------------------------------

class TestSanitizeSkillName:
    """Test sanitize_skill_name function."""

    def test_simple_name_passes_through(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("my-skill")
        assert result == "my-skill"

    def test_uppercase_converted_to_lowercase(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("MySkill")
        assert result == "myskill"

    def test_spaces_converted_to_hyphens(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("my skill name")
        assert result == "my-skill-name"

    def test_underscores_converted_to_hyphens(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("my_skill_name")
        assert result == "my-skill-name"

    def test_special_chars_removed(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("my-skill!@#$")
        assert result == "my-skill"

    def test_empty_string_raises_validation_error(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name
        from ii_agent.agent.runtime.skills.skills_ref.errors import ValidationError

        with pytest.raises(ValidationError):
            sanitize_skill_name("")

    def test_none_raises_validation_error(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name
        from ii_agent.agent.runtime.skills.skills_ref.errors import ValidationError

        with pytest.raises(ValidationError):
            sanitize_skill_name(None)

    def test_only_special_chars_raises_validation_error(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name
        from ii_agent.agent.runtime.skills.skills_ref.errors import ValidationError

        with pytest.raises(ValidationError):
            sanitize_skill_name("!@#$%")

    def test_long_name_truncated(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name, MAX_SKILL_NAME_LENGTH

        long_name = "a" * 100
        result = sanitize_skill_name(long_name)
        assert len(result) <= MAX_SKILL_NAME_LENGTH

    def test_unicode_name_handled(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("café skill")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_multiple_hyphens_collapsed(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("my---skill")
        assert "--" not in result

    def test_leading_trailing_hyphens_stripped(self):
        from ii_agent.agent.runtime.skills.github import sanitize_skill_name

        result = sanitize_skill_name("-my-skill-")
        assert not result.startswith("-")
        assert not result.endswith("-")


class TestGitHubDownloadServiceParseURL:
    """Test GitHubDownloadService.parse_url."""

    def _make_service(self):
        from ii_agent.agent.runtime.skills.github import GitHubDownloadService

        return GitHubDownloadService()

    def test_valid_url_parsed(self):
        service = self._make_service()
        result = service.parse_url("https://github.com/owner/repo/tree/main/skills/brand")
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.branch == "main"
        assert result.path == "skills/brand"

    def test_invalid_url_raises_parse_error(self):
        from ii_agent.agent.runtime.skills.github import GitHubURLParseError

        service = self._make_service()
        with pytest.raises(GitHubURLParseError):
            service.parse_url("https://not-github.com/owner/repo")

    def test_url_with_trailing_slash_stripped(self):
        service = self._make_service()
        result = service.parse_url("https://github.com/owner/repo/tree/main/path/")
        assert not result.path.endswith("/")

    def test_url_with_deep_path(self):
        service = self._make_service()
        result = service.parse_url("https://github.com/owner/repo/tree/main/deep/nested/skill")
        assert result.path == "deep/nested/skill"

    def test_url_with_feature_branch(self):
        service = self._make_service()
        result = service.parse_url("https://github.com/owner/repo/tree/feature/my-branch/skills/test")
        assert result.owner == "owner"
