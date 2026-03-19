"""Unit tests for GitHub connector tool."""

import json
import base64
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agent.runtime.tools.connectors.github import GitHubAgentTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tool(
    github_token="token123",
    github_metadata=None,
    default_repository=None,
) -> GitHubAgentTool:
    return GitHubAgentTool(
        github_token=github_token,
        workspace_path="/workspace",
        github_metadata=github_metadata or {},
        default_repository=default_repository,
    )


def make_http_response(json_data=None, status_code=200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.raise_for_status = MagicMock()
    response.text = json.dumps(json_data or {})
    return response


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------

class TestGitHubAgentToolInit:
    def test_init_sets_attributes(self):
        tool = make_tool(github_token="my-token")
        assert tool.github_token == "my-token"
        assert tool.name == "github"
        assert tool.display_name == "GitHub"
        assert tool.read_only is False

    def test_init_no_default_repository(self):
        tool = make_tool()
        assert tool.default_repository is None
        assert "DEFAULT REPOSITORY" not in tool.description

    def test_init_with_default_repository(self):
        repo = {"full_name": "owner/repo", "default_branch": "main", "owner": "owner", "name": "repo"}
        tool = make_tool(default_repository=repo)
        assert "owner/repo" in tool.description
        assert "main" in tool.description

    def test_input_schema_has_required_action(self):
        tool = make_tool()
        assert "action" in tool.input_schema["properties"]
        assert tool.input_schema["required"] == ["action"]

    def test_sandbox_initially_none(self):
        tool = make_tool()
        assert tool.sandbox is None

    def test_github_metadata_defaults_to_empty_dict(self):
        tool = make_tool()
        assert tool.github_metadata == {}

    def test_base_url_is_github_api(self):
        tool = make_tool()
        assert tool._base_url == "https://api.github.com"

    def test_description_contains_action_list(self):
        tool = make_tool()
        assert "list_repos" in tool.description
        assert "create_issue" in tool.description
        assert "clone_repo" in tool.description


# ---------------------------------------------------------------------------
# _get_repo_context tests
# ---------------------------------------------------------------------------

class TestGetRepoContext:
    def test_explicit_owner_and_repo(self):
        tool = make_tool()
        owner, repo = tool._get_repo_context({"owner": "myowner", "repo": "myrepo"})
        assert owner == "myowner"
        assert repo == "myrepo"

    def test_falls_back_to_default_repository(self):
        default_repo = {"owner": "default_owner", "name": "default_repo"}
        tool = make_tool(default_repository=default_repo)
        owner, repo = tool._get_repo_context({})
        assert owner == "default_owner"
        assert repo == "default_repo"

    def test_raises_when_no_repo_and_no_default(self):
        tool = make_tool()
        with pytest.raises(ValueError, match="No repository specified"):
            tool._get_repo_context({})

    def test_explicit_owner_overrides_default(self):
        default_repo = {"owner": "default_owner", "name": "default_repo"}
        tool = make_tool(default_repository=default_repo)
        owner, repo = tool._get_repo_context({"owner": "explicit_owner"})
        assert owner == "explicit_owner"
        assert repo == "default_repo"

    def test_explicit_repo_overrides_default(self):
        default_repo = {"owner": "default_owner", "name": "default_repo"}
        tool = make_tool(default_repository=default_repo)
        owner, repo = tool._get_repo_context({"repo": "explicit_repo"})
        assert owner == "default_owner"
        assert repo == "explicit_repo"


# ---------------------------------------------------------------------------
# execute routing tests
# ---------------------------------------------------------------------------

class TestExecuteRouting:
    @pytest.mark.asyncio
    async def test_execute_missing_action_returns_error(self):
        tool = make_tool()
        result = await tool.execute({})
        assert result.is_error is True
        assert "action" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_unknown_action_returns_error(self):
        tool = make_tool()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await tool.execute({"action": "unknown_action"})
            assert result.is_error is True
            assert "unknown_action" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_handles_http_status_error(self):
        import httpx
        tool = make_tool()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_response)
            )
            mock_client_class.return_value = mock_client

            result = await tool.execute({"action": "list_repos"})
            assert result.is_error is True


# ---------------------------------------------------------------------------
# _list_repos tests
# ---------------------------------------------------------------------------

class TestListRepos:
    @pytest.mark.asyncio
    async def test_list_repos_formats_output(self):
        tool = make_tool()
        mock_client = AsyncMock()
        repos = [
            {"full_name": "owner/repo1", "html_url": "http://github.com/owner/repo1"},
            {"full_name": "owner/repo2", "html_url": "http://github.com/owner/repo2"},
        ]
        mock_client.get = AsyncMock(return_value=make_http_response(repos))
        headers = {}

        result = await tool._list_repos(mock_client, headers, {})
        assert "owner/repo1" in result
        assert "owner/repo2" in result
        assert "Found 2 repositories" in result

    @pytest.mark.asyncio
    async def test_list_repos_uses_per_page_param(self):
        tool = make_tool()
        mock_client = AsyncMock()
        response = make_http_response([])
        response.json.return_value = []  # Return list, not dict
        mock_client.get = AsyncMock(return_value=response)
        await tool._list_repos(mock_client, {}, {"per_page": 50})
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["per_page"] == 50


# ---------------------------------------------------------------------------
# _get_repo tests
# ---------------------------------------------------------------------------

class TestGetRepo:
    @pytest.mark.asyncio
    async def test_get_repo_returns_json(self):
        tool = make_tool()
        mock_client = AsyncMock()
        repo_data = {"name": "myrepo", "full_name": "owner/myrepo"}
        mock_client.get = AsyncMock(return_value=make_http_response(repo_data))

        result = await tool._get_repo(mock_client, {}, {"owner": "owner", "repo": "myrepo"})
        parsed = json.loads(result)
        assert parsed["name"] == "myrepo"


# ---------------------------------------------------------------------------
# _get_file tests
# ---------------------------------------------------------------------------

class TestGetFile:
    @pytest.mark.asyncio
    async def test_get_file_requires_path(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="path"):
            await tool._get_file(mock_client, {}, {"owner": "owner", "repo": "repo"})

    @pytest.mark.asyncio
    async def test_get_file_returns_decoded_content(self):
        tool = make_tool()
        mock_client = AsyncMock()
        content = base64.b64encode(b"hello world").decode("utf-8")
        file_data = {"content": content}
        mock_client.get = AsyncMock(return_value=make_http_response(file_data))

        result = await tool._get_file(mock_client, {}, {"owner": "owner", "repo": "repo", "path": "README.md"})
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_get_file_directory_returns_info(self):
        tool = make_tool()
        mock_client = AsyncMock()
        dir_data = [{"name": "file1.py"}, {"name": "file2.py"}]
        mock_client.get = AsyncMock(return_value=make_http_response(dir_data))

        result = await tool._get_file(mock_client, {}, {"owner": "owner", "repo": "repo", "path": "src"})
        assert "directory" in result.lower()


# ---------------------------------------------------------------------------
# _list_issues tests
# ---------------------------------------------------------------------------

class TestListIssues:
    @pytest.mark.asyncio
    async def test_list_issues_formats_output(self):
        tool = make_tool()
        mock_client = AsyncMock()
        issues = [{"number": 1, "title": "Bug report", "state": "open"}]
        mock_client.get = AsyncMock(return_value=make_http_response(issues))

        result = await tool._list_issues(mock_client, {}, {"owner": "owner", "repo": "repo"})
        assert "#1" in result
        assert "Bug report" in result

    @pytest.mark.asyncio
    async def test_list_issues_default_state_open(self):
        tool = make_tool()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=make_http_response([]))
        await tool._list_issues(mock_client, {}, {"owner": "owner", "repo": "repo"})
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["state"] == "open"


# ---------------------------------------------------------------------------
# _get_issue tests
# ---------------------------------------------------------------------------

class TestGetIssue:
    @pytest.mark.asyncio
    async def test_get_issue_requires_issue_number(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="issue_number"):
            await tool._get_issue(mock_client, {}, {"owner": "owner", "repo": "repo"})

    @pytest.mark.asyncio
    async def test_get_issue_returns_json(self):
        tool = make_tool()
        mock_client = AsyncMock()
        issue_data = {"number": 5, "title": "My Issue"}
        mock_client.get = AsyncMock(return_value=make_http_response(issue_data))

        result = await tool._get_issue(mock_client, {}, {"owner": "o", "repo": "r", "issue_number": 5})
        parsed = json.loads(result)
        assert parsed["number"] == 5


# ---------------------------------------------------------------------------
# _create_issue tests
# ---------------------------------------------------------------------------

class TestCreateIssue:
    @pytest.mark.asyncio
    async def test_create_issue_posts_and_returns_url(self):
        tool = make_tool()
        mock_client = AsyncMock()
        issue = {"number": 10, "html_url": "http://github.com/owner/repo/issues/10"}
        mock_client.post = AsyncMock(return_value=make_http_response(issue))

        result = await tool._create_issue(mock_client, {}, {
            "owner": "owner", "repo": "repo",
            "title": "New Issue", "body": "Issue body"
        })
        assert "10" in result
        assert "http://github.com" in result

    @pytest.mark.asyncio
    async def test_create_issue_includes_labels_if_provided(self):
        tool = make_tool()
        mock_client = AsyncMock()
        issue = {"number": 11, "html_url": "http://github.com/owner/repo/issues/11"}
        mock_client.post = AsyncMock(return_value=make_http_response(issue))

        await tool._create_issue(mock_client, {}, {
            "owner": "o", "repo": "r",
            "title": "Test", "body": "Body",
            "labels": ["bug"],
        })
        post_kwargs = mock_client.post.call_args[1]
        assert "labels" in post_kwargs["json"]
        assert post_kwargs["json"]["labels"] == ["bug"]


# ---------------------------------------------------------------------------
# _list_prs tests
# ---------------------------------------------------------------------------

class TestListPrs:
    @pytest.mark.asyncio
    async def test_list_prs_formats_output(self):
        tool = make_tool()
        mock_client = AsyncMock()
        prs = [{"number": 3, "title": "Feature PR", "state": "open"}]
        mock_client.get = AsyncMock(return_value=make_http_response(prs))

        result = await tool._list_prs(mock_client, {}, {"owner": "o", "repo": "r"})
        assert "#3" in result
        assert "Feature PR" in result


# ---------------------------------------------------------------------------
# _create_pr tests
# ---------------------------------------------------------------------------

class TestCreatePr:
    @pytest.mark.asyncio
    async def test_create_pr_returns_url(self):
        tool = make_tool()
        mock_client = AsyncMock()
        pr = {"number": 7, "html_url": "http://github.com/owner/repo/pull/7"}
        mock_client.post = AsyncMock(return_value=make_http_response(pr))

        result = await tool._create_pr(mock_client, {}, {
            "owner": "owner", "repo": "repo",
            "title": "New PR", "head": "feature", "base": "main", "body": "PR body"
        })
        assert "7" in result
        assert "http://github.com" in result


# ---------------------------------------------------------------------------
# _create_commit tests
# ---------------------------------------------------------------------------

class TestCreateCommit:
    @pytest.mark.asyncio
    async def test_create_commit_requires_branch(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="branch"):
            await tool._create_commit(mock_client, {}, {"owner": "o", "repo": "r", "message": "msg", "files": []})

    @pytest.mark.asyncio
    async def test_create_commit_requires_message(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="message"):
            await tool._create_commit(mock_client, {}, {"owner": "o", "repo": "r", "branch": "main", "files": []})

    @pytest.mark.asyncio
    async def test_create_commit_requires_files(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="files"):
            await tool._create_commit(mock_client, {}, {"owner": "o", "repo": "r", "branch": "main", "message": "msg", "files": []})

    @pytest.mark.asyncio
    async def test_create_commit_validates_file_structure(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="path.*content"):
            await tool._create_commit(mock_client, {}, {
                "owner": "o", "repo": "r",
                "branch": "main", "message": "msg",
                "files": [{"path": "only-path"}]
            })


# ---------------------------------------------------------------------------
# _search_code tests
# ---------------------------------------------------------------------------

class TestSearchCode:
    @pytest.mark.asyncio
    async def test_search_code_requires_query(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="query"):
            await tool._search_code(mock_client, {}, {})

    @pytest.mark.asyncio
    async def test_search_code_formats_output(self):
        tool = make_tool()
        mock_client = AsyncMock()
        results = {
            "total_count": 2,
            "items": [
                {"repository": {"full_name": "owner/repo1"}, "path": "src/file1.py"},
                {"repository": {"full_name": "owner/repo2"}, "path": "src/file2.py"},
            ]
        }
        mock_client.get = AsyncMock(return_value=make_http_response(results))

        result = await tool._search_code(mock_client, {}, {"query": "def my_function"})
        assert "2" in result
        assert "owner/repo1" in result


# ---------------------------------------------------------------------------
# _list_branches tests
# ---------------------------------------------------------------------------

class TestListBranches:
    @pytest.mark.asyncio
    async def test_list_branches_formats_output(self):
        tool = make_tool()
        mock_client = AsyncMock()
        branches = [{"name": "main"}, {"name": "develop"}]
        mock_client.get = AsyncMock(return_value=make_http_response(branches))

        result = await tool._list_branches(mock_client, {}, {"owner": "o", "repo": "r"})
        assert "main" in result
        assert "develop" in result


# ---------------------------------------------------------------------------
# _create_branch tests
# ---------------------------------------------------------------------------

class TestCreateBranch:
    @pytest.mark.asyncio
    async def test_create_branch_requires_branch_name(self):
        tool = make_tool()
        mock_client = AsyncMock()
        with pytest.raises(ValueError, match="branch"):
            await tool._create_branch(mock_client, {}, {"owner": "o", "repo": "r"})

    @pytest.mark.asyncio
    async def test_create_branch_with_from_branch(self):
        tool = make_tool()
        mock_client = AsyncMock()

        ref_response = make_http_response({"object": {"sha": "abc123"}})
        create_ref_response = make_http_response({"ref": "refs/heads/new-branch"})

        mock_client.get = AsyncMock(return_value=ref_response)
        mock_client.post = AsyncMock(return_value=create_ref_response)

        result = await tool._create_branch(mock_client, {}, {
            "owner": "o", "repo": "r",
            "branch": "new-branch",
            "from_branch": "main",
        })
        assert "new-branch" in result
        assert "main" in result


# ---------------------------------------------------------------------------
# _get_readme tests
# ---------------------------------------------------------------------------

class TestGetReadme:
    @pytest.mark.asyncio
    async def test_get_readme_decodes_content(self):
        tool = make_tool()
        mock_client = AsyncMock()
        content = base64.b64encode(b"# My README").decode("utf-8")
        readme_data = {"content": content}
        mock_client.get = AsyncMock(return_value=make_http_response(readme_data))

        result = await tool._get_readme(mock_client, {}, {"owner": "o", "repo": "r"})
        assert "# My README" in result


# ---------------------------------------------------------------------------
# _create_issue_comment tests
# ---------------------------------------------------------------------------

class TestCreateIssueComment:
    @pytest.mark.asyncio
    async def test_create_issue_comment_posts_and_confirms(self):
        tool = make_tool()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=make_http_response({"id": 1}))

        result = await tool._create_issue_comment(mock_client, {}, {
            "owner": "o", "repo": "r",
            "issue_number": 5,
            "body": "Test comment",
        })
        assert "5" in result
        assert "Comment added" in result


# ---------------------------------------------------------------------------
# _create_pr_review tests
# ---------------------------------------------------------------------------

class TestCreatePrReview:
    @pytest.mark.asyncio
    async def test_create_pr_review_defaults_to_comment(self):
        tool = make_tool()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=make_http_response({"id": 1}))

        result = await tool._create_pr_review(mock_client, {}, {
            "owner": "o", "repo": "r",
            "pr_number": 3,
            "body": "LGTM",
        })
        assert "3" in result
        post_data = mock_client.post.call_args[1]["json"]
        assert post_data["event"] == "COMMENT"
