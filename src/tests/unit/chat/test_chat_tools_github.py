"""Unit tests for ii_agent.chat.tools.github – GitHubTool."""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ii_agent.chat.tools.github import GitHubTool
from ii_agent.chat.tools.base import ToolCallInput
from ii_agent.chat.types import ErrorTextContent, TextResultContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(
    github_token: str = "ghp_test_token",
    github_metadata: dict = None,
    default_repository: dict = None,
) -> GitHubTool:
    return GitHubTool(
        github_token=github_token,
        github_metadata=github_metadata,
        default_repository=default_repository,
    )


def _tool_call(action: str, **kwargs) -> ToolCallInput:
    params = {"action": action, **kwargs}
    return ToolCallInput(id="tc-1", name="github", input=json.dumps(params))


def _mock_response(data, status_code: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with JSON body."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json = MagicMock(return_value=data)
    response.raise_for_status = MagicMock()
    return response


def _mock_http_error(status_code: int) -> httpx.HTTPStatusError:
    request = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    return httpx.HTTPStatusError("HTTP error", request=request, response=response)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestGitHubToolInit:
    def test_can_instantiate_with_token(self):
        tool = _make_tool()
        assert tool.github_token == "ghp_test_token"

    def test_can_instantiate_without_token(self):
        tool = _make_tool(github_token=None)
        assert tool.github_token is None

    def test_name_property(self):
        tool = _make_tool()
        assert tool.name == "github"

    def test_base_url(self):
        tool = _make_tool()
        assert tool._base_url == "https://api.github.com"

    def test_stores_default_repository(self):
        repo = {
            "owner": "myorg",
            "name": "myrepo",
            "full_name": "myorg/myrepo",
            "default_branch": "main",
        }
        tool = _make_tool(default_repository=repo)
        assert tool.default_repository == repo

    def test_github_metadata_defaults_to_empty_dict(self):
        tool = _make_tool(github_metadata=None)
        assert tool.github_metadata == {}


# ---------------------------------------------------------------------------
# info()
# ---------------------------------------------------------------------------


class TestGitHubToolInfo:
    def test_info_returns_tool_info(self):
        from ii_agent.chat.tools.base import ToolInfo

        tool = _make_tool()
        info = tool.info()
        assert isinstance(info, ToolInfo)
        assert info.name == "github"

    def test_info_required_is_action(self):
        tool = _make_tool()
        info = tool.info()
        assert info.required == ["action"]

    def test_info_includes_all_actions(self):
        tool = _make_tool()
        info = tool.info()
        actions = info.parameters["properties"]["action"]["enum"]
        expected_actions = [
            "list_repos",
            "get_repo",
            "list_commits",
            "get_file",
            "list_issues",
            "get_issue",
            "create_issue",
            "create_issue_comment",
            "list_prs",
            "get_pr",
            "create_pr",
            "create_pr_comment",
            "create_pr_review",
            "create_commit",
            "search_code",
            "list_branches",
            "create_branch",
            "get_readme",
        ]
        for action in expected_actions:
            assert action in actions

    def test_info_description_mentions_default_repo(self):
        default_repo = {"full_name": "myorg/myrepo", "default_branch": "main"}
        tool = _make_tool(default_repository=default_repo)
        info = tool.info()
        assert "myorg/myrepo" in info.description

    def test_info_description_no_default_repo_mention_when_absent(self):
        tool = _make_tool(default_repository=None)
        info = tool.info()
        assert "DEFAULT REPOSITORY" not in info.description


# ---------------------------------------------------------------------------
# run() – no token
# ---------------------------------------------------------------------------


class TestGitHubToolRunNoToken:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_token(self):
        tool = _make_tool(github_token=None)
        call = _tool_call("list_repos")
        response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "GitHub is not connected" in response.output.value

    @pytest.mark.asyncio
    async def test_returns_error_when_empty_token(self):
        tool = _make_tool(github_token="")
        call = _tool_call("list_repos")
        response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)


# ---------------------------------------------------------------------------
# run() – invalid input
# ---------------------------------------------------------------------------


class TestGitHubToolRunInvalidInput:
    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_json(self):
        tool = _make_tool()
        call = ToolCallInput(id="tc-1", name="github", input="NOT JSON")
        response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "Invalid tool input" in response.output.value

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_action(self):
        tool = _make_tool()
        call = _tool_call("nonexistent_action")

        # We need to mock httpx since the tool still creates an async client
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            response = await tool.run(call)

        assert isinstance(response.output, ErrorTextContent)
        assert "Unknown action" in response.output.value


# ---------------------------------------------------------------------------
# run() – default repository injection
# ---------------------------------------------------------------------------


class TestDefaultRepositoryInjection:
    @pytest.mark.asyncio
    async def test_injects_default_owner_when_missing(self):
        default_repo = {"owner": "defaultowner", "name": "defaultrepo", "default_branch": "main"}
        tool = _make_tool(default_repository=default_repo)

        mock_repos = [
            {
                "name": "r",
                "full_name": "defaultowner/r",
                "description": "",
                "private": False,
                "html_url": "https://github.com/r",
                "default_branch": "main",
                "language": None,
                "updated_at": "2024-01-01",
            }
        ]

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(return_value=_mock_response(mock_repos))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            call = _tool_call("list_repos")
            await tool.run(call)


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


class TestGitHubToolHttpErrors:
    @pytest.mark.asyncio
    async def test_returns_timeout_error_message(self):
        tool = _make_tool()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            call = _tool_call("list_repos")
            response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "timed out" in response.output.value

    @pytest.mark.asyncio
    async def test_returns_401_error_message(self):
        tool = _make_tool()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=_mock_http_error(401))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            call = _tool_call("list_repos")
            response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "authentication" in response.output.value.lower()

    @pytest.mark.asyncio
    async def test_returns_403_error_message(self):
        tool = _make_tool()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=_mock_http_error(403))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            call = _tool_call("list_repos")
            response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert (
            "rate limit" in response.output.value.lower()
            or "permissions" in response.output.value.lower()
        )

    @pytest.mark.asyncio
    async def test_returns_404_error_message(self):
        tool = _make_tool()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=_mock_http_error(404))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            call = _tool_call("list_repos")
            response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "not found" in response.output.value.lower()

    @pytest.mark.asyncio
    async def test_returns_generic_error_message_on_unexpected_exception(self):
        tool = _make_tool()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(side_effect=RuntimeError("unexpected"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            call = _tool_call("list_repos")
            response = await tool.run(call)
        assert isinstance(response.output, ErrorTextContent)
        assert "Unexpected error" in response.output.value


# ---------------------------------------------------------------------------
# _list_repos – response shaping
# ---------------------------------------------------------------------------


class TestListRepos:
    @pytest.mark.asyncio
    async def test_returns_shaped_repo_list(self):
        tool = _make_tool()
        raw_repos = [
            {
                "name": "myrepo",
                "full_name": "user/myrepo",
                "description": "A repo",
                "private": False,
                "html_url": "https://github.com/user/myrepo",
                "default_branch": "main",
                "language": "Python",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(raw_repos))
        headers = {}
        result = await tool._list_repos(mock_client, headers, {"per_page": 30})
        assert len(result) == 1
        assert result[0]["name"] == "myrepo"
        assert "html_url" in result[0]

    @pytest.mark.asyncio
    async def test_caps_per_page_at_100(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response([]))
        await tool._list_repos(mock_client, {}, {"per_page": 500})
        call_kwargs = mock_client.get.call_args
        # per_page is passed in params
        params = (
            call_kwargs[1]["params"]
            if call_kwargs[1]
            else call_kwargs[0][1]
            if len(call_kwargs[0]) > 1
            else {}
        )
        assert params.get("per_page", 500) <= 100


# ---------------------------------------------------------------------------
# _get_repo – validation
# ---------------------------------------------------------------------------


class TestGetRepo:
    @pytest.mark.asyncio
    async def test_raises_when_owner_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="owner"):
            await tool._get_repo(mock_client, {}, {"repo": "myrepo"})

    @pytest.mark.asyncio
    async def test_raises_when_repo_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="repo"):
            await tool._get_repo(mock_client, {}, {"owner": "myuser"})

    @pytest.mark.asyncio
    async def test_returns_shaped_repo_data(self):
        tool = _make_tool()
        raw_repo = {
            "name": "myrepo",
            "full_name": "user/myrepo",
            "description": "desc",
            "private": False,
            "html_url": "https://github.com/user/myrepo",
            "default_branch": "main",
            "language": "Python",
            "topics": ["python"],
            "stargazers_count": 10,
            "forks_count": 2,
            "open_issues_count": 1,
            "created_at": "2020-01-01",
            "updated_at": "2024-01-01",
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(raw_repo))
        result = await tool._get_repo(mock_client, {}, {"owner": "user", "repo": "myrepo"})
        assert result["name"] == "myrepo"
        assert "stargazers_count" in result


# ---------------------------------------------------------------------------
# _get_file – directory vs file handling
# ---------------------------------------------------------------------------


class TestGetFile:
    @pytest.mark.asyncio
    async def test_raises_when_path_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="path"):
            await tool._get_file(mock_client, {}, {"owner": "u", "repo": "r"})

    @pytest.mark.asyncio
    async def test_handles_directory_listing(self):
        tool = _make_tool()
        dir_listing = [
            {"name": "file1.py", "type": "file", "path": "src/file1.py"},
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(dir_listing))
        result = await tool._get_file(mock_client, {}, {"owner": "u", "repo": "r", "path": "src"})
        assert result["type"] == "directory"
        assert "contents" in result

    @pytest.mark.asyncio
    async def test_decodes_base64_file_content(self):
        tool = _make_tool()
        raw_content = "Hello World"
        encoded = base64.b64encode(raw_content.encode()).decode()
        file_data = {
            "name": "readme.md",
            "path": "readme.md",
            "size": len(raw_content),
            "encoding": "base64",
            "content": encoded + "\n",  # GitHub adds newlines
            "html_url": "https://github.com/u/r/readme.md",
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(file_data))
        result = await tool._get_file(
            mock_client, {}, {"owner": "u", "repo": "r", "path": "readme.md"}
        )
        assert result["type"] == "file"
        assert raw_content in result["content"]


# ---------------------------------------------------------------------------
# _list_issues – PR filtering
# ---------------------------------------------------------------------------


class TestListIssues:
    @pytest.mark.asyncio
    async def test_filters_out_pull_requests(self):
        tool = _make_tool()
        issues = [
            {
                "number": 1,
                "title": "Bug",
                "state": "open",
                "user": {"login": "alice"},
                "labels": [],
                "created_at": "2024-01-01",
                "html_url": "https://github.com/u/r/issues/1",
            },
            {
                "number": 2,
                "title": "PR",
                "state": "open",
                "user": {"login": "bob"},
                "labels": [],
                "created_at": "2024-01-01",
                "html_url": "https://github.com/u/r/pull/2",
                "pull_request": {"url": "..."},  # This marks it as a PR
            },
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(issues))
        result = await tool._list_issues(mock_client, {}, {"owner": "u", "repo": "r"})
        assert len(result) == 1
        assert result[0]["number"] == 1


# ---------------------------------------------------------------------------
# _create_issue – validation
# ---------------------------------------------------------------------------


class TestCreateIssue:
    @pytest.mark.asyncio
    async def test_raises_when_title_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="title"):
            await tool._create_issue(mock_client, {}, {"owner": "u", "repo": "r"})

    @pytest.mark.asyncio
    async def test_creates_issue_with_optional_fields(self):
        tool = _make_tool()
        created = {
            "number": 5,
            "title": "New issue",
            "state": "open",
            "body": "desc",
            "user": {"login": "alice"},
            "labels": [],
            "html_url": "https://github.com/u/r/issues/5",
            "created_at": "2024-01-01",
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(created))
        result = await tool._create_issue(
            mock_client,
            {},
            {
                "owner": "u",
                "repo": "r",
                "title": "New issue",
                "body": "desc",
                "labels": ["bug"],
                "assignees": ["alice"],
            },
        )
        assert result["number"] == 5
        call_json = mock_client.post.call_args[1]["json"]
        assert "labels" in call_json
        assert "assignees" in call_json


# ---------------------------------------------------------------------------
# _create_pr – validation
# ---------------------------------------------------------------------------


class TestCreatePr:
    @pytest.mark.asyncio
    async def test_raises_when_head_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="head"):
            await tool._create_pr(
                mock_client,
                {},
                {"owner": "u", "repo": "r", "title": "PR", "base": "main"},
            )

    @pytest.mark.asyncio
    async def test_raises_when_base_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="base"):
            await tool._create_pr(
                mock_client,
                {},
                {"owner": "u", "repo": "r", "title": "PR", "head": "feature"},
            )


# ---------------------------------------------------------------------------
# _search_code – validation
# ---------------------------------------------------------------------------


class TestSearchCode:
    @pytest.mark.asyncio
    async def test_raises_when_query_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="query"):
            await tool._search_code(mock_client, {}, {})

    @pytest.mark.asyncio
    async def test_returns_shaped_search_results(self):
        tool = _make_tool()
        raw_result = {
            "total_count": 1,
            "items": [
                {
                    "name": "main.py",
                    "path": "src/main.py",
                    "repository": {"full_name": "u/r"},
                    "html_url": "https://github.com/u/r/src/main.py",
                }
            ],
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(raw_result))
        result = await tool._search_code(mock_client, {}, {"query": "def main"})
        assert result["total_count"] == 1
        assert result["items"][0]["name"] == "main.py"


# ---------------------------------------------------------------------------
# _list_branches
# ---------------------------------------------------------------------------


class TestListBranches:
    @pytest.mark.asyncio
    async def test_raises_when_owner_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError):
            await tool._list_branches(mock_client, {}, {"repo": "r"})

    @pytest.mark.asyncio
    async def test_returns_branch_list(self):
        tool = _make_tool()
        raw_branches = [
            {"name": "main", "protected": True},
            {"name": "develop", "protected": False},
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(raw_branches))
        result = await tool._list_branches(mock_client, {}, {"owner": "u", "repo": "r"})
        assert len(result) == 2
        assert result[0]["name"] == "main"
        assert "protected" in result[0]


# ---------------------------------------------------------------------------
# _get_readme – decoding
# ---------------------------------------------------------------------------


class TestGetReadme:
    @pytest.mark.asyncio
    async def test_raises_when_owner_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError):
            await tool._get_readme(mock_client, {}, {"repo": "r"})

    @pytest.mark.asyncio
    async def test_decodes_base64_content(self):
        tool = _make_tool()
        readme_text = "# My Project\n\nA great project."
        encoded = base64.b64encode(readme_text.encode()).decode()
        raw_data = {
            "name": "README.md",
            "path": "README.md",
            "content": encoded + "\n",
            "html_url": "https://github.com/u/r/README.md",
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(raw_data))
        result = await tool._get_readme(mock_client, {}, {"owner": "u", "repo": "r"})
        assert result["name"] == "README.md"
        assert "# My Project" in result["content"]


# ---------------------------------------------------------------------------
# _list_commits – shaping
# ---------------------------------------------------------------------------


class TestListCommits:
    @pytest.mark.asyncio
    async def test_raises_when_owner_missing(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError):
            await tool._list_commits(mock_client, {}, {"repo": "r"})

    @pytest.mark.asyncio
    async def test_returns_first_line_of_commit_message(self):
        tool = _make_tool()
        raw_commits = [
            {
                "sha": "abcdef1234567890",
                "commit": {
                    "message": "First line\n\nLong body",
                    "author": {"name": "Alice", "date": "2024-01-01"},
                },
                "html_url": "https://github.com/u/r/commit/abc",
            }
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(raw_commits))
        result = await tool._list_commits(mock_client, {}, {"owner": "u", "repo": "r"})
        assert len(result) == 1
        assert result[0]["message"] == "First line"
        assert result[0]["sha"] == "abcdef1"  # First 7 chars
