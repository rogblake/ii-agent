"""Unit tests for GitHub connector tool and MCP tools - r4.

Covers:
- GitHubAgentTool.__init__ / description building
- GitHubAgentTool._get_repo_context
- GitHubAgentTool.execute (action routing, error handling)
- GitHubAgentTool._list_repos, _get_repo, _list_commits, _get_file, etc.
- MCPTool.__init__ and execute (no mcp_client, tool error, normal flow)
- ComposioMCPTool.__init__ and execute
- mcp_tool_loader.load_tools_from_mcp
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import Any

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# GitHubAgentTool helpers
# ---------------------------------------------------------------------------

def _make_github_tool(token="test-token", default_repo=None, github_metadata=None):
    from ii_agent.agent.runtime.tools.connectors.github import GitHubAgentTool

    workspace = MagicMock()
    workspace.container_workspace = "/workspace"

    return GitHubAgentTool(
        github_token=token,
        workspace_manager=workspace,
        github_metadata=github_metadata or {},
        default_repository=default_repo,
    )


# ---------------------------------------------------------------------------
# GitHubAgentTool initialization
# ---------------------------------------------------------------------------

class TestGitHubAgentToolInit:
    """Test GitHubAgentTool initialization."""

    def test_basic_init(self):
        tool = _make_github_tool()
        assert tool.github_token == "test-token"
        assert tool.name == "github"
        assert tool.display_name == "GitHub"
        assert tool.read_only is False

    def test_input_schema_has_action(self):
        tool = _make_github_tool()
        assert "action" in tool.input_schema["properties"]

    def test_description_with_default_repo(self):
        default_repo = {
            "full_name": "owner/repo",
            "default_branch": "main",
            "owner": "owner",
            "name": "repo",
        }
        tool = _make_github_tool(default_repo=default_repo)
        assert "DEFAULT REPOSITORY" in tool.description
        assert "owner/repo" in tool.description

    def test_description_without_default_repo(self):
        tool = _make_github_tool()
        assert "DEFAULT REPOSITORY" not in tool.description
        assert "Available actions:" in tool.description

    def test_sandbox_initially_none(self):
        tool = _make_github_tool()
        assert tool.sandbox is None


# ---------------------------------------------------------------------------
# GitHubAgentTool._get_repo_context
# ---------------------------------------------------------------------------

class TestGitHubGetRepoContext:
    """Test _get_repo_context."""

    def test_uses_provided_owner_and_repo(self):
        tool = _make_github_tool()
        owner, repo = tool._get_repo_context({"owner": "myowner", "repo": "myrepo"})
        assert owner == "myowner"
        assert repo == "myrepo"

    def test_falls_back_to_default_repo(self):
        tool = _make_github_tool(default_repo={"owner": "defowner", "name": "defrepo"})
        owner, repo = tool._get_repo_context({})
        assert owner == "defowner"
        assert repo == "defrepo"

    def test_partial_override_uses_default_for_missing(self):
        tool = _make_github_tool(default_repo={"owner": "defowner", "name": "defrepo"})
        owner, repo = tool._get_repo_context({"owner": "myowner"})
        assert owner == "myowner"
        assert repo == "defrepo"

    def test_raises_without_default_and_no_input(self):
        tool = _make_github_tool()
        with pytest.raises(ValueError, match="No repository specified"):
            tool._get_repo_context({})


# ---------------------------------------------------------------------------
# GitHubAgentTool.execute - routing
# ---------------------------------------------------------------------------

class TestGitHubAgentToolExecute:
    """Test execute method routing and error handling."""

    @pytest.mark.asyncio
    async def test_missing_action_returns_error(self):
        tool = _make_github_tool()
        result = await tool.execute({})
        assert result.is_error is True
        assert "action" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        tool = _make_github_tool()
        result = await tool.execute({"action": "unknown_action"})
        assert result.is_error is True
        assert "Unknown action" in result.llm_content

    @pytest.mark.asyncio
    async def test_list_repos_routes_to_handler(self):
        tool = _make_github_tool()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=[
            {"full_name": "owner/repo", "html_url": "http://github.com/owner/repo"}
        ])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "list_repos"})

        assert result.is_error is not True
        assert "repo" in result.llm_content.lower() or "found" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_http_status_error_returns_error_result(self):
        import httpx

        tool = _make_github_tool()

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        http_error = httpx.HTTPStatusError("403", request=MagicMock(), response=mock_response)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=http_error)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "list_repos"})

        assert result.is_error is True
        assert "GitHub API error" in result.llm_content

    @pytest.mark.asyncio
    async def test_generic_exception_returns_error(self):
        tool = _make_github_tool()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("Network failure"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "list_repos"})

        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_get_repo_action(self):
        tool = _make_github_tool(default_repo={"owner": "owner", "name": "repo"})

        repo_data = {"name": "repo", "full_name": "owner/repo", "description": "A repo"}
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=repo_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "get_repo"})

        assert result.is_error is not True
        assert "repo" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_list_issues_action(self):
        tool = _make_github_tool(default_repo={"owner": "owner", "name": "repo"})

        issues = [
            {"number": 1, "title": "Bug fix", "state": "open", "html_url": "http://..."},
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=issues)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "list_issues"})

        assert result.is_error is not True

    @pytest.mark.asyncio
    async def test_get_file_action_returns_content(self):
        import base64

        tool = _make_github_tool(default_repo={"owner": "owner", "name": "repo"})

        file_content = base64.b64encode(b"print('hello')").decode("utf-8")
        file_data = {"name": "main.py", "content": file_content + "\n"}

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=file_data)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "get_file", "path": "main.py"})

        assert result.is_error is not True
        assert "hello" in result.llm_content

    @pytest.mark.asyncio
    async def test_get_file_missing_path_raises(self):
        tool = _make_github_tool(default_repo={"owner": "owner", "name": "repo"})

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(side_effect=ValueError("path required"))

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "get_file"})

        # Missing path should produce an error
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_list_commits_action(self):
        tool = _make_github_tool(default_repo={"owner": "owner", "name": "repo"})

        commits = [
            {
                "sha": "abc1234",
                "commit": {
                    "message": "Initial commit",
                    "author": {"name": "Dev"},
                },
            }
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=commits)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "list_commits"})

        assert result.is_error is not True
        assert "abc1234"[:4] in result.llm_content or "commit" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_list_branches_action(self):
        tool = _make_github_tool(default_repo={"owner": "owner", "name": "repo"})

        branches = [{"name": "main"}, {"name": "develop"}]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=branches)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute({"action": "list_branches"})

        assert result.is_error is not True


# ---------------------------------------------------------------------------
# MCPTool
# ---------------------------------------------------------------------------

class TestMCPTool:
    """Test MCPTool class."""

    def _make_mcp_tool(self, **kwargs):
        from ii_agent.agent.runtime.tools.mcp.base import MCPTool

        defaults = dict(
            name="test_mcp",
            display_name="Test MCP",
            description="A test MCP tool",
            input_schema={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            read_only=True,
        )
        defaults.update(kwargs)
        return MCPTool(**defaults)

    def test_init_sets_attributes(self):
        tool = self._make_mcp_tool()
        assert tool.name == "test_mcp"
        assert tool.display_name == "Test MCP"
        assert tool.description == "A test MCP tool"
        assert tool.read_only is True
        assert tool.mcp_client is None

    def test_init_openai_custom_type_sets_format(self):
        from ii_agent.agent.runtime.tools.mcp.base import MCPTool

        schema = {"type": "object", "properties": {}}
        tool = MCPTool(
            name="custom",
            display_name="Custom",
            description="Custom tool",
            input_schema=schema,
            read_only=False,
            type="openai_custom",
        )
        assert hasattr(tool, "format")

    @pytest.mark.asyncio
    async def test_execute_returns_error_when_no_mcp_client(self):
        tool = self._make_mcp_tool()
        tool.mcp_client = None
        result = await tool.execute({"x": "test"})
        assert result.is_error is True
        assert "not ready" in result.llm_content.lower() or "MCP" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_with_text_content(self):
        tool = self._make_mcp_tool()

        # Setup mcp_client mock
        text_result = MagicMock()
        text_result.type = "text"
        text_result.text = "Tool executed successfully"

        mcp_call_result = MagicMock()
        mcp_call_result.content = [text_result]
        mcp_call_result.structured_content = None

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=mcp_call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"x": "test"})
        assert result.is_error is not True
        assert "Tool executed successfully" in result.llm_content or \
               isinstance(result.llm_content, list)

    @pytest.mark.asyncio
    async def test_execute_with_tool_error(self):
        from fastmcp.exceptions import ToolError

        tool = self._make_mcp_tool()

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=ToolError("Tool failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"x": "test"})
        assert result.is_error is True
        assert "Tool failed" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_with_general_exception(self):
        tool = self._make_mcp_tool()

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=RuntimeError("Connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"x": "test"})
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_execute_with_image_content(self):
        tool = self._make_mcp_tool()

        img_result = MagicMock()
        img_result.type = "image"
        img_result.data = "base64data"
        img_result.mimeType = "image/png"

        mcp_call_result = MagicMock()
        mcp_call_result.content = [img_result]
        mcp_call_result.structured_content = None

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=mcp_call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"x": "test"})
        # Should have image content
        assert result.is_error is not True
        assert isinstance(result.llm_content, list)

    @pytest.mark.asyncio
    async def test_execute_with_unknown_content_type_raises(self):
        tool = self._make_mcp_tool()

        unknown_result = MagicMock()
        unknown_result.type = "unknown_type"

        mcp_call_result = MagicMock()
        mcp_call_result.content = [unknown_result]
        mcp_call_result.structured_content = None

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=mcp_call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"x": "test"})
        # Unknown type causes error
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_execute_uses_structured_content_user_display(self):
        tool = self._make_mcp_tool()

        text_result = MagicMock()
        text_result.type = "text"
        text_result.text = "result text"

        mcp_call_result = MagicMock()
        mcp_call_result.content = [text_result]
        mcp_call_result.structured_content = {
            "user_display_content": {"key": "value"},
            "is_error": False,
        }

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=mcp_call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"x": "test"})
        assert result.user_display_content == {"key": "value"}
        assert result.is_error is False


# ---------------------------------------------------------------------------
# ComposioMCPTool
# ---------------------------------------------------------------------------

class TestComposioMCPTool:
    """Test ComposioMCPTool."""

    def _make_composio_tool(self):
        from ii_agent.agent.runtime.tools.mcp.composio_mcp import ComposioMCPTool

        return ComposioMCPTool(
            name="github_STARS",
            display_name="GitHub Stars",
            description="Star a GitHub repo",
            input_schema={"type": "object", "properties": {"repo": {"type": "string"}}, "required": ["repo"]},
            read_only=False,
            mcp_server_id="composio-server",
        )

    def test_init_sets_name(self):
        tool = self._make_composio_tool()
        assert tool.name == "github_STARS"

    def test_init_sets_mcp_server_id(self):
        tool = self._make_composio_tool()
        assert tool.mcp_server_id == "composio-server"

    @pytest.mark.asyncio
    async def test_execute_calls_composio_prefixed_name(self):
        tool = self._make_composio_tool()

        text_result = MagicMock()
        text_result.type = "text"
        text_result.text = "Starred!"

        mcp_call_result = MagicMock()
        mcp_call_result.content = [text_result]
        mcp_call_result.structured_content = None

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value=mcp_call_result)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"repo": "owner/repo"})

        # Verify called with composio prefix
        call_args = mock_client.call_tool.call_args
        assert "mcp_composio_github_STARS" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_execute_tool_error_returns_error_result(self):
        from fastmcp.exceptions import ToolError

        tool = self._make_composio_tool()

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=ToolError("Composio error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        tool.mcp_client = mock_client

        result = await tool.execute({"repo": "test"})
        assert result.is_error is True
        assert "Composio error" in result.llm_content

    def test_tool_logo_default_none(self):
        tool = self._make_composio_tool()
        assert tool.tool_logo is None

    def test_init_with_logo(self):
        from ii_agent.agent.runtime.tools.mcp.composio_mcp import ComposioMCPTool

        tool = ComposioMCPTool(
            name="test",
            display_name="Test",
            description="Test",
            input_schema={"type": "object", "properties": {}, "required": []},
            read_only=False,
            tool_logo="https://example.com/logo.png",
        )
        assert tool.tool_logo == "https://example.com/logo.png"


# ---------------------------------------------------------------------------
# mcp_tool_loader.load_tools_from_mcp
# ---------------------------------------------------------------------------

class TestMCPToolLoader:
    """Test load_tools_from_mcp function."""

    @pytest.mark.asyncio
    async def test_loads_tools_from_mcp_server(self):
        from ii_agent.agent.runtime.tools.mcp.mcp_tool_loader import load_tools_from_mcp
        from ii_agent.agent.runtime.tools.mcp.user_mcp_tool import UserMCPTool

        tool1 = MagicMock()
        tool1.name = "tool_one"
        tool1.description = "First tool"
        tool1.inputSchema = {"type": "object", "properties": {}}
        tool1.annotations = None

        tool2 = MagicMock()
        tool2.name = "tool_two"
        tool2.description = "Second tool"
        tool2.inputSchema = {"type": "object", "properties": {"x": {"type": "string"}}}
        annotations = MagicMock()
        annotations.title = "Tool Two"
        annotations.readOnlyHint = True
        tool2.annotations = annotations

        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[tool1, tool2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.transport = MagicMock()
        mock_client.transport.close = AsyncMock()

        with patch("ii_agent.agent.runtime.tools.mcp.mcp_tool_loader.Client", return_value=mock_client):
            tools = await load_tools_from_mcp("http://localhost:8080/mcp")

        assert len(tools) == 2
        assert all(isinstance(t, UserMCPTool) for t in tools)

    @pytest.mark.asyncio
    async def test_skips_tool_without_description(self):
        from ii_agent.agent.runtime.tools.mcp.mcp_tool_loader import load_tools_from_mcp

        tool_no_desc = MagicMock()
        tool_no_desc.name = "no_desc_tool"
        tool_no_desc.description = None

        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[tool_no_desc])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.transport = MagicMock()
        mock_client.transport.close = AsyncMock()

        with patch("ii_agent.agent.runtime.tools.mcp.mcp_tool_loader.Client", return_value=mock_client):
            tools = await load_tools_from_mcp("http://localhost:8080/mcp")

        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_returns_empty_on_connection_error(self):
        from ii_agent.agent.runtime.tools.mcp.mcp_tool_loader import load_tools_from_mcp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("Cannot connect"))
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("ii_agent.agent.runtime.tools.mcp.mcp_tool_loader.Client", return_value=mock_client):
            tools = await load_tools_from_mcp("http://localhost:8080/mcp")

        assert tools == []

    @pytest.mark.asyncio
    async def test_tool_annotations_read_only_hint(self):
        from ii_agent.agent.runtime.tools.mcp.mcp_tool_loader import load_tools_from_mcp

        tool = MagicMock()
        tool.name = "readonly_tool"
        tool.description = "A read-only tool"
        tool.inputSchema = {"type": "object", "properties": {}}
        annotations = MagicMock()
        annotations.title = "Read Only"
        annotations.readOnlyHint = True
        tool.annotations = annotations

        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[tool])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.transport = MagicMock()
        mock_client.transport.close = AsyncMock()

        with patch("ii_agent.agent.runtime.tools.mcp.mcp_tool_loader.Client", return_value=mock_client):
            tools = await load_tools_from_mcp("http://localhost:8080/mcp", mcp_server_id="server-1")

        assert len(tools) == 1
        assert tools[0].read_only is True
        assert tools[0].display_name == "Read Only"

    @pytest.mark.asyncio
    async def test_tool_no_read_only_hint_defaults_to_false(self):
        from ii_agent.agent.runtime.tools.mcp.mcp_tool_loader import load_tools_from_mcp

        tool = MagicMock()
        tool.name = "normal_tool"
        tool.description = "Normal tool"
        tool.inputSchema = {"type": "object", "properties": {}}
        annotations = MagicMock()
        annotations.title = None
        annotations.readOnlyHint = None
        tool.annotations = annotations

        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[tool])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.transport = MagicMock()
        mock_client.transport.close = AsyncMock()

        with patch("ii_agent.agent.runtime.tools.mcp.mcp_tool_loader.Client", return_value=mock_client):
            tools = await load_tools_from_mcp("http://localhost:8080/mcp")

        assert len(tools) == 1
        assert tools[0].read_only is False

    @pytest.mark.asyncio
    async def test_inner_transport_closed_after_loading(self):
        from ii_agent.agent.runtime.tools.mcp.mcp_tool_loader import load_tools_from_mcp

        inner_transport = MagicMock()
        inner_transport.close = AsyncMock()

        outer_transport = MagicMock()
        outer_transport.transport = inner_transport

        mock_client = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.transport = outer_transport

        with patch("ii_agent.agent.runtime.tools.mcp.mcp_tool_loader.Client", return_value=mock_client):
            await load_tools_from_mcp("http://localhost:8080/mcp")

        inner_transport.close.assert_called_once()
