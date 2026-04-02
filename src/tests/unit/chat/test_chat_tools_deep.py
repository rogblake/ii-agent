"""Deep unit tests for ii_agent.chat.tools.github (GitHubTool)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ii_agent.chat.tools.github import GitHubTool
from ii_agent.chat.types import ErrorTextContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(token="ghp_test", default_repo=None, metadata=None) -> GitHubTool:
    return GitHubTool(
        github_token=token,
        github_metadata=metadata or {},
        default_repository=default_repo,
    )


def _tool_call(action: str, **kwargs) -> "ToolCallInput":  # noqa: F821
    from ii_agent.chat.tools.base import ToolCallInput

    payload = {"action": action, **kwargs}
    return ToolCallInput(input=json.dumps(payload), id="call-1", name="github")


def _mock_response(data, status=200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = data
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# No token
# ---------------------------------------------------------------------------


class TestNoToken:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_token(self):
        tool = _make_tool(token=None)
        result = await tool.run(_tool_call("list_repos"))
        assert isinstance(result.output, ErrorTextContent)
        assert "not connected" in result.output.value.lower() or "GitHub" in result.output.value

    @pytest.mark.asyncio
    async def test_returns_error_for_empty_token(self):
        tool = _make_tool(token="")
        result = await tool.run(_tool_call("list_repos"))
        assert isinstance(result.output, ErrorTextContent)


# ---------------------------------------------------------------------------
# Invalid JSON input
# ---------------------------------------------------------------------------


class TestInvalidInput:
    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_json(self):
        tool = _make_tool()
        from ii_agent.chat.tools.base import ToolCallInput

        bad_call = ToolCallInput(input="not-json", id="c-1", name="github")
        result = await tool.run(bad_call)
        assert isinstance(result.output, ErrorTextContent)


# ---------------------------------------------------------------------------
# Unknown action
# ---------------------------------------------------------------------------


class TestUnknownAction:
    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_action(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.run(_tool_call("unknown_action"))
        assert isinstance(result.output, ErrorTextContent)
        assert "Unknown action" in result.output.value


# ---------------------------------------------------------------------------
# Default repository injection
# ---------------------------------------------------------------------------


class TestDefaultRepository:
    def test_tool_info_includes_default_repo(self):
        default_repo = {
            "owner": "myorg",
            "name": "myrepo",
            "full_name": "myorg/myrepo",
            "default_branch": "main",
        }
        tool = _make_tool(default_repo=default_repo)
        info = tool.info()
        assert "myorg/myrepo" in info.description

    @pytest.mark.asyncio
    async def test_applies_default_owner_repo_when_missing(self):
        default_repo = {
            "owner": "myorg",
            "name": "myrepo",
            "full_name": "myorg/myrepo",
            "default_branch": "main",
        }
        tool = _make_tool(default_repo=default_repo)

        captured_params = {}

        async def fake_list_repos(client, headers, params):
            captured_params.update(params)
            return []

        with patch.object(tool, "_list_repos", new=fake_list_repos):
            async_client = AsyncMock()
            async_client.__aenter__ = AsyncMock(return_value=async_client)
            async_client.__aexit__ = AsyncMock(return_value=None)
            with patch("httpx.AsyncClient", return_value=async_client):
                await tool.run(_tool_call("list_repos"))

    @pytest.mark.asyncio
    async def test_applies_default_branch_for_get_file(self):
        default_repo = {
            "owner": "o",
            "name": "r",
            "full_name": "o/r",
            "default_branch": "develop",
        }
        tool = _make_tool(default_repo=default_repo)
        captured_params = {}

        async def fake_get_file(client, headers, params):
            captured_params.update(params)
            return {"type": "file", "content": ""}

        with patch.object(tool, "_get_file", new=fake_get_file):
            async_client = AsyncMock()
            async_client.__aenter__ = AsyncMock(return_value=async_client)
            async_client.__aexit__ = AsyncMock(return_value=None)
            with patch("httpx.AsyncClient", return_value=async_client):
                await tool.run(_tool_call("get_file", path="README.md"))

        assert captured_params.get("branch") == "develop"


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------


class TestHTTPErrors:
    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.run(_tool_call("list_repos"))

        assert isinstance(result.output, ErrorTextContent)
        assert "timed out" in result.output.value.lower()

    @pytest.mark.asyncio
    async def test_handles_401(self):
        tool = _make_tool()
        mock_resp = _mock_response({}, status=401)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Unauthorized",
                request=MagicMock(),
                response=mock_resp,
            )
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.run(_tool_call("list_repos"))

        assert isinstance(result.output, ErrorTextContent)
        assert "authentication" in result.output.value.lower() or "401" in result.output.value

    @pytest.mark.asyncio
    async def test_handles_403(self):
        tool = _make_tool()
        mock_resp = _mock_response({}, status=403)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Forbidden",
                request=MagicMock(),
                response=mock_resp,
            )
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.run(_tool_call("list_repos"))

        assert isinstance(result.output, ErrorTextContent)
        assert "rate limit" in result.output.value.lower() or "403" in result.output.value

    @pytest.mark.asyncio
    async def test_handles_404(self):
        tool = _make_tool()
        mock_resp = _mock_response({}, status=404)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                message="Not Found",
                request=MagicMock(),
                response=mock_resp,
            )
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.run(_tool_call("list_repos"))

        assert isinstance(result.output, ErrorTextContent)
        assert "not found" in result.output.value.lower() or "404" in result.output.value

    @pytest.mark.asyncio
    async def test_handles_generic_exception(self):
        tool = _make_tool()
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=RuntimeError("Unexpected!"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await tool.run(_tool_call("list_repos"))

        assert isinstance(result.output, ErrorTextContent)
        assert "Unexpected!" in result.output.value


# ---------------------------------------------------------------------------
# _list_repos
# ---------------------------------------------------------------------------


class TestListRepos:
    @pytest.mark.asyncio
    async def test_returns_repo_list(self):
        tool = _make_tool()
        repos = [
            {
                "name": "repo1",
                "full_name": "user/repo1",
                "description": "desc",
                "private": False,
                "html_url": "https://github.com/user/repo1",
                "default_branch": "main",
                "language": "Python",
                "updated_at": "2024-01-01",
            }
        ]
        mock_resp = _mock_response(repos)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._list_repos(mock_client, {}, {"per_page": 30})
        assert len(result) == 1
        assert result[0]["name"] == "repo1"

    @pytest.mark.asyncio
    async def test_caps_per_page_at_100(self):
        tool = _make_tool()
        mock_resp = _mock_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        await tool._list_repos(mock_client, {}, {"per_page": 500})
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["params"]["per_page"] == 100


# ---------------------------------------------------------------------------
# _get_repo
# ---------------------------------------------------------------------------


class TestGetRepo:
    @pytest.mark.asyncio
    async def test_raises_value_error_without_owner(self):
        tool = _make_tool()
        with pytest.raises(ValueError, match="owner and repo"):
            await tool._get_repo(AsyncMock(), {}, {"repo": "test"})

    @pytest.mark.asyncio
    async def test_returns_repo_details(self):
        tool = _make_tool()
        data = {
            "name": "myrepo",
            "full_name": "owner/myrepo",
            "description": "A repo",
            "private": False,
            "html_url": "https://github.com/owner/myrepo",
            "default_branch": "main",
            "language": "Python",
            "topics": ["api"],
            "stargazers_count": 10,
            "forks_count": 2,
            "open_issues_count": 5,
            "created_at": "2024-01-01",
            "updated_at": "2024-06-01",
        }
        mock_resp = _mock_response(data)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._get_repo(mock_client, {}, {"owner": "owner", "repo": "myrepo"})
        assert result["name"] == "myrepo"
        assert result["stargazers_count"] == 10


# ---------------------------------------------------------------------------
# _list_commits
# ---------------------------------------------------------------------------


class TestListCommits:
    @pytest.mark.asyncio
    async def test_raises_without_required_params(self):
        tool = _make_tool()
        with pytest.raises(ValueError):
            await tool._list_commits(AsyncMock(), {}, {"owner": "o"})

    @pytest.mark.asyncio
    async def test_includes_branch_param(self):
        tool = _make_tool()
        mock_resp = _mock_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        await tool._list_commits(mock_client, {}, {"owner": "o", "repo": "r", "branch": "feature"})
        call_kwargs = mock_client.get.call_args
        assert call_kwargs.kwargs["params"]["sha"] == "feature"


# ---------------------------------------------------------------------------
# _get_file
# ---------------------------------------------------------------------------


class TestGetFile:
    @pytest.mark.asyncio
    async def test_raises_without_path(self):
        tool = _make_tool()
        with pytest.raises(ValueError):
            await tool._get_file(AsyncMock(), {}, {"owner": "o", "repo": "r"})

    @pytest.mark.asyncio
    async def test_handles_directory_response(self):
        tool = _make_tool()
        data = [
            {"name": "file1.py", "type": "file", "path": "src/file1.py"},
        ]
        mock_resp = _mock_response(data)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._get_file(mock_client, {}, {"owner": "o", "repo": "r", "path": "src"})
        assert result["type"] == "directory"
        assert len(result["contents"]) == 1

    @pytest.mark.asyncio
    async def test_handles_base64_file_content(self):
        import base64

        tool = _make_tool()
        content = base64.b64encode(b"hello world").decode("utf-8")
        data = {
            "name": "README.md",
            "path": "README.md",
            "size": 11,
            "encoding": "base64",
            "content": content + "\n",
            "html_url": "https://github.com/o/r/blob/main/README.md",
        }
        mock_resp = _mock_response(data)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._get_file(
            mock_client, {}, {"owner": "o", "repo": "r", "path": "README.md"}
        )
        assert result["content"] == "hello world"
        assert result["type"] == "file"

    @pytest.mark.asyncio
    async def test_handles_non_base64_content(self):
        tool = _make_tool()
        data = {
            "name": "README.md",
            "path": "README.md",
            "size": 5,
            "encoding": "utf-8",
            "content": "hello",
            "html_url": "https://github.com/o/r/blob/main/README.md",
        }
        mock_resp = _mock_response(data)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._get_file(
            mock_client, {}, {"owner": "o", "repo": "r", "path": "README.md"}
        )
        assert result["content"] == "hello"


# ---------------------------------------------------------------------------
# _list_issues
# ---------------------------------------------------------------------------


class TestListIssues:
    @pytest.mark.asyncio
    async def test_filters_pull_requests(self):
        tool = _make_tool()
        issues = [
            {
                "number": 1,
                "title": "Bug",
                "state": "open",
                "user": {"login": "alice"},
                "labels": [],
                "created_at": "2024-01-01",
                "html_url": "https://github.com/o/r/issues/1",
            },
            {
                "number": 2,
                "title": "PR",
                "state": "open",
                "user": {"login": "bob"},
                "labels": [],
                "created_at": "2024-01-02",
                "html_url": "https://github.com/o/r/pull/2",
                "pull_request": {"url": "..."},
            },
        ]
        mock_resp = _mock_response(issues)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._list_issues(mock_client, {}, {"owner": "o", "repo": "r"})
        assert len(result) == 1
        assert result[0]["number"] == 1


# ---------------------------------------------------------------------------
# _create_issue
# ---------------------------------------------------------------------------


class TestCreateIssue:
    @pytest.mark.asyncio
    async def test_raises_without_title(self):
        tool = _make_tool()
        with pytest.raises(ValueError):
            await tool._create_issue(AsyncMock(), {}, {"owner": "o", "repo": "r"})

    @pytest.mark.asyncio
    async def test_includes_labels_and_assignees(self):
        tool = _make_tool()
        issue_data = {
            "number": 5,
            "title": "Test",
            "state": "open",
            "body": "body",
            "user": {"login": "alice"},
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/o/r/issues/5",
            "created_at": "2024-01-01",
        }
        mock_resp = _mock_response(issue_data)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        result = await tool._create_issue(
            mock_client,
            {},
            {
                "owner": "o",
                "repo": "r",
                "title": "Test",
                "labels": ["bug"],
                "assignees": ["bob"],
            },
        )
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["labels"] == ["bug"]
        assert payload["assignees"] == ["bob"]
        assert result["number"] == 5


# ---------------------------------------------------------------------------
# _create_commit
# ---------------------------------------------------------------------------


class TestCreateCommit:
    @pytest.mark.asyncio
    async def test_raises_without_required_params(self):
        tool = _make_tool()
        with pytest.raises(ValueError):
            await tool._create_commit(AsyncMock(), {}, {"owner": "o", "repo": "r"})

    @pytest.mark.asyncio
    async def test_includes_author_when_provided(self):
        tool = _make_tool()

        ref_resp = _mock_response({"object": {"sha": "abc123"}})
        commit_resp = _mock_response({"tree": {"sha": "tree123"}})
        blob_resp = _mock_response({"sha": "blob123"})
        tree_resp = _mock_response({"sha": "new-tree-sha"})
        new_commit_resp = _mock_response(
            {
                "sha": "new-commit-sha",
                "author": {"name": "Author", "date": "2024-01-01"},
                "html_url": "https://github.com/o/r/commit/new-commit-sha",
            }
        )
        update_ref_resp = _mock_response({})

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[ref_resp, commit_resp])
        mock_client.post = AsyncMock(side_effect=[blob_resp, tree_resp, new_commit_resp])
        mock_client.patch = AsyncMock(return_value=update_ref_resp)

        result = await tool._create_commit(
            mock_client,
            {},
            {
                "owner": "o",
                "repo": "r",
                "branch": "main",
                "message": "test commit",
                "files": [{"path": "file.txt", "content": "hello"}],
                "author_name": "Author",
                "author_email": "author@example.com",
            },
        )
        # Check the commit payload included author info
        new_commit_call_kwargs = mock_client.post.call_args_list[2]
        payload = new_commit_call_kwargs.kwargs["json"]
        assert "author" in payload
        assert payload["author"]["name"] == "Author"


# ---------------------------------------------------------------------------
# _search_code
# ---------------------------------------------------------------------------


class TestSearchCode:
    @pytest.mark.asyncio
    async def test_raises_without_query(self):
        tool = _make_tool()
        with pytest.raises(ValueError, match="query"):
            await tool._search_code(AsyncMock(), {}, {})

    @pytest.mark.asyncio
    async def test_returns_search_results(self):
        tool = _make_tool()
        data = {
            "total_count": 1,
            "items": [
                {
                    "name": "file.py",
                    "path": "src/file.py",
                    "repository": {"full_name": "o/r"},
                    "html_url": "https://github.com/o/r/blob/main/src/file.py",
                }
            ],
        }
        mock_resp = _mock_response(data)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._search_code(mock_client, {}, {"query": "test"})
        assert result["total_count"] == 1
        assert result["items"][0]["name"] == "file.py"


# ---------------------------------------------------------------------------
# _create_branch
# ---------------------------------------------------------------------------


class TestCreateBranch:
    @pytest.mark.asyncio
    async def test_raises_without_owner(self):
        tool = _make_tool()
        with pytest.raises(ValueError):
            await tool._create_branch(AsyncMock(), {}, {"branch": "new"})

    @pytest.mark.asyncio
    async def test_raises_without_branch(self):
        tool = _make_tool()
        with pytest.raises(ValueError, match="branch"):
            await tool._create_branch(AsyncMock(), {}, {"owner": "o", "repo": "r"})

    @pytest.mark.asyncio
    async def test_fetches_default_branch_when_from_branch_missing(self):
        tool = _make_tool()
        repo_resp = _mock_response({"default_branch": "main"})
        ref_resp = _mock_response({"object": {"sha": "abc123"}})
        create_resp = _mock_response({})

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[repo_resp, ref_resp])
        mock_client.post = AsyncMock(return_value=create_resp)

        result = await tool._create_branch(
            mock_client,
            {},
            {"owner": "o", "repo": "r", "branch": "feature"},
        )
        assert result["branch"] == "feature"
        assert result["from_branch"] == "main"

    @pytest.mark.asyncio
    async def test_uses_provided_from_branch(self):
        tool = _make_tool()
        ref_resp = _mock_response({"object": {"sha": "xyz789"}})
        create_resp = _mock_response({})

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=ref_resp)
        mock_client.post = AsyncMock(return_value=create_resp)

        result = await tool._create_branch(
            mock_client,
            {},
            {"owner": "o", "repo": "r", "branch": "new-feat", "from_branch": "develop"},
        )
        assert result["from_branch"] == "develop"


# ---------------------------------------------------------------------------
# _get_readme
# ---------------------------------------------------------------------------


class TestGetReadme:
    @pytest.mark.asyncio
    async def test_raises_without_owner(self):
        tool = _make_tool()
        with pytest.raises(ValueError):
            await tool._get_readme(AsyncMock(), {}, {"repo": "r"})

    @pytest.mark.asyncio
    async def test_decodes_base64_content(self):
        import base64

        tool = _make_tool()
        content = base64.b64encode(b"# README").decode("utf-8")
        data = {
            "name": "README.md",
            "path": "README.md",
            "content": content + "\n",
            "html_url": "https://github.com/o/r/blob/main/README.md",
        }
        mock_resp = _mock_response(data)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await tool._get_readme(mock_client, {}, {"owner": "o", "repo": "r"})
        assert result["content"] == "# README"


# ---------------------------------------------------------------------------
# Tool info (no token)
# ---------------------------------------------------------------------------


class TestToolInfo:
    def test_returns_tool_info_without_default_repo(self):
        tool = _make_tool(default_repo=None)
        info = tool.info()
        assert info.name == "github"
        assert "list_repos" in info.description

    def test_name_property(self):
        tool = _make_tool()
        assert tool.name == "github"
