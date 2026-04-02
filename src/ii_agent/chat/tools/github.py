"""GitHub tool - enables agent to access user's GitHub repositories."""

import json
import httpx
from typing import Optional

from ii_agent.chat.types import ErrorTextContent, TextResultContent

from .base import BaseTool, ToolInfo, ToolCallInput, ToolResponse


class GitHubTool(BaseTool):
    """Access GitHub repositories and perform operations."""

    def __init__(
        self,
        github_token: Optional[str],
        github_metadata: Optional[dict] = None,
        default_repository: Optional[dict] = None,
    ):
        self.github_token = github_token
        self.github_metadata = github_metadata or {}
        self.default_repository = default_repository  # {"owner": "...", "name": "...", "full_name": "...", "default_branch": "..."}
        self._name = "github"
        self._base_url = "https://api.github.com"

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        # Build description with default repository context if available
        base_description = "Access GitHub repositories to perform various operations. "

        if self.default_repository:
            base_description += f"\n\nDEFAULT REPOSITORY: {self.default_repository.get('full_name', 'N/A')} (branch: {self.default_repository.get('default_branch', 'main')}). "
            base_description += (
                "When owner/repo are not specified, this repository will be used automatically.\n\n"
            )

        base_description += (
            "Available actions:\n"
            "- list_repos: List user's accessible repositories\n"
            "- get_repo: Get repository details (uses default repo if owner/repo not specified)\n"
            "- list_commits: List recent commits (uses default repo if owner/repo not specified; optional: branch, per_page)\n"
            "- get_file: Get file content (uses default repo if owner/repo not specified; requires: path; optional: branch)\n"
            "- list_issues: List repository issues (uses default repo if owner/repo not specified; optional: state, per_page)\n"
            "- get_issue: Get issue details (uses default repo if owner/repo not specified; requires: issue_number)\n"
            "- create_issue: Create a new issue (uses default repo if owner/repo not specified; requires: title, body; optional: labels, assignees)\n"
            "- create_issue_comment: Add a comment to an issue (uses default repo if owner/repo not specified; requires: issue_number, body)\n"
            "- list_prs: List pull requests (uses default repo if owner/repo not specified; optional: state, per_page)\n"
            "- get_pr: Get pull request details (uses default repo if owner/repo not specified; requires: pr_number)\n"
            "- create_pr: Create a new pull request (uses default repo if owner/repo not specified; requires: title, head, base, body)\n"
            "- create_pr_comment: Add a comment to a pull request (uses default repo if owner/repo not specified; requires: pr_number, body)\n"
            "- create_pr_review: Create a review on a pull request (uses default repo if owner/repo not specified; requires: pr_number, body; optional: event)\n"
            "- create_commit: Create a commit with file changes (uses default repo if owner/repo not specified; requires: branch, message, files; optional: author_name, author_email)\n"
            "- search_code: Search code in repositories (requires: query; optional: per_page)\n"
            "- list_branches: List repository branches (uses default repo if owner/repo not specified)\n"
            "- create_branch: Create a new branch (uses default repo if owner/repo not specified; requires: branch; optional: from_branch)\n"
            "- get_readme: Get repository README (uses default repo if owner/repo not specified)"
        )

        return ToolInfo(
            name="github",
            description=base_description,
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The GitHub action to perform",
                        "enum": [
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
                        ],
                    },
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "path": {
                        "type": "string",
                        "description": "File path in repository",
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch name (defaults to default branch)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query for code search",
                    },
                    "state": {
                        "type": "string",
                        "description": "State filter for issues/PRs (open, closed, all)",
                        "enum": ["open", "closed", "all"],
                    },
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue number",
                    },
                    "pr_number": {
                        "type": "integer",
                        "description": "Pull request number",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Number of results per page (max 100)",
                    },
                    "body": {
                        "type": "string",
                        "description": "Comment or review body text (supports markdown)",
                    },
                    "event": {
                        "type": "string",
                        "description": "Review event type for create_pr_review",
                        "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    },
                    "title": {
                        "type": "string",
                        "description": "Title for issue or pull request",
                    },
                    "head": {
                        "type": "string",
                        "description": "The name of the branch where your changes are (for create_pr)",
                    },
                    "base": {
                        "type": "string",
                        "description": "The name of the branch you want to merge into (for create_pr)",
                    },
                    "labels": {
                        "type": "array",
                        "description": "Array of label names for issues",
                        "items": {"type": "string"},
                    },
                    "assignees": {
                        "type": "array",
                        "description": "Array of usernames to assign to issues",
                        "items": {"type": "string"},
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message",
                    },
                    "files": {
                        "type": "array",
                        "description": "Array of file changes for commit. Each file should have 'path', 'content', and optionally 'mode' (100644 for regular file, 100755 for executable)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"},
                                "mode": {"type": "string"},
                            },
                        },
                    },
                    "author_name": {
                        "type": "string",
                        "description": "Author name for commit (optional, uses authenticated user if not specified)",
                    },
                    "author_email": {
                        "type": "string",
                        "description": "Author email for commit (optional, uses authenticated user if not specified)",
                    },
                    "from_branch": {
                        "type": "string",
                        "description": "Source branch to create new branch from (defaults to default branch)",
                    },
                },
            },
            required=["action"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        # Check if GitHub is connected
        if not self.github_token:
            return ToolResponse(
                output=ErrorTextContent(
                    value="GitHub is not connected. Please connect your GitHub account in Settings to use this feature."
                )
            )

        try:
            params = json.loads(tool_call.input)
            action = params.get("action")
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        # Apply default repository if owner/repo not specified
        if self.default_repository:
            if not params.get("owner"):
                params["owner"] = self.default_repository.get("owner")
            if not params.get("repo"):
                params["repo"] = self.default_repository.get("name")
            if not params.get("branch") and action in ["list_commits", "get_file"]:
                params["branch"] = self.default_repository.get("default_branch")

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }

                if action == "list_repos":
                    result = await self._list_repos(client, headers, params)
                elif action == "get_repo":
                    result = await self._get_repo(client, headers, params)
                elif action == "list_commits":
                    result = await self._list_commits(client, headers, params)
                elif action == "get_file":
                    result = await self._get_file(client, headers, params)
                elif action == "list_issues":
                    result = await self._list_issues(client, headers, params)
                elif action == "get_issue":
                    result = await self._get_issue(client, headers, params)
                elif action == "create_issue":
                    result = await self._create_issue(client, headers, params)
                elif action == "create_issue_comment":
                    result = await self._create_issue_comment(client, headers, params)
                elif action == "list_prs":
                    result = await self._list_prs(client, headers, params)
                elif action == "get_pr":
                    result = await self._get_pr(client, headers, params)
                elif action == "create_pr":
                    result = await self._create_pr(client, headers, params)
                elif action == "create_pr_comment":
                    result = await self._create_pr_comment(client, headers, params)
                elif action == "create_pr_review":
                    result = await self._create_pr_review(client, headers, params)
                elif action == "create_commit":
                    result = await self._create_commit(client, headers, params)
                elif action == "search_code":
                    result = await self._search_code(client, headers, params)
                elif action == "list_branches":
                    result = await self._list_branches(client, headers, params)
                elif action == "create_branch":
                    result = await self._create_branch(client, headers, params)
                elif action == "get_readme":
                    result = await self._get_readme(client, headers, params)
                else:
                    return ToolResponse(output=ErrorTextContent(value=f"Unknown action: {action}"))

                return ToolResponse(output=TextResultContent(value=json.dumps(result, indent=2)))

        except httpx.TimeoutException:
            return ToolResponse(
                output=ErrorTextContent(value="GitHub API request timed out. Please try again.")
            )
        except httpx.HTTPStatusError as e:
            error_msg = f"GitHub API error: {e.response.status_code}"
            if e.response.status_code == 401:
                error_msg = "GitHub authentication failed. Please reconnect your GitHub account."
            elif e.response.status_code == 403:
                error_msg = "GitHub API rate limit exceeded or insufficient permissions."
            elif e.response.status_code == 404:
                error_msg = "Resource not found. Please check the repository/file path."
            return ToolResponse(output=ErrorTextContent(value=error_msg))
        except Exception as e:
            return ToolResponse(output=ErrorTextContent(value=f"Unexpected error: {str(e)}"))

    async def _list_repos(self, client: httpx.AsyncClient, headers: dict, params: dict) -> list:
        """List user's accessible repositories."""
        per_page = min(params.get("per_page", 30), 100)
        response = await client.get(
            f"{self._base_url}/user/repos",
            headers=headers,
            params={"per_page": per_page, "sort": "updated"},
            timeout=30,
        )
        response.raise_for_status()
        repos = response.json()
        return [
            {
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description"),
                "private": r["private"],
                "html_url": r["html_url"],
                "default_branch": r["default_branch"],
                "language": r.get("language"),
                "updated_at": r["updated_at"],
            }
            for r in repos
        ]

    async def _get_repo(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Get repository details."""
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required for get_repo")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        r = response.json()
        return {
            "name": r["name"],
            "full_name": r["full_name"],
            "description": r.get("description"),
            "private": r["private"],
            "html_url": r["html_url"],
            "default_branch": r["default_branch"],
            "language": r.get("language"),
            "topics": r.get("topics", []),
            "stargazers_count": r["stargazers_count"],
            "forks_count": r["forks_count"],
            "open_issues_count": r["open_issues_count"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    async def _list_commits(self, client: httpx.AsyncClient, headers: dict, params: dict) -> list:
        """List recent commits in repository."""
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required for list_commits")

        per_page = min(params.get("per_page", 20), 100)
        query_params = {"per_page": per_page}
        if params.get("branch"):
            query_params["sha"] = params["branch"]

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/commits",
            headers=headers,
            params=query_params,
            timeout=30,
        )
        response.raise_for_status()
        commits = response.json()
        return [
            {
                "sha": c["sha"][:7],
                "message": c["commit"]["message"].split("\n")[0],  # First line only
                "author": c["commit"]["author"]["name"],
                "date": c["commit"]["author"]["date"],
                "html_url": c["html_url"],
            }
            for c in commits
        ]

    async def _get_file(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Get file content from repository."""
        owner = params.get("owner")
        repo = params.get("repo")
        path = params.get("path")
        if not owner or not repo or not path:
            raise ValueError("owner, repo, and path are required for get_file")

        query_params = {}
        if params.get("branch"):
            query_params["ref"] = params["branch"]

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
            params=query_params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Handle directory listing
        if isinstance(data, list):
            return {
                "type": "directory",
                "path": path,
                "contents": [
                    {"name": item["name"], "type": item["type"], "path": item["path"]}
                    for item in data
                ],
            }

        # Handle file content
        if data.get("encoding") == "base64":
            import base64

            content = base64.b64decode(data["content"]).decode("utf-8")
        else:
            content = data.get("content", "")

        return {
            "type": "file",
            "name": data["name"],
            "path": data["path"],
            "size": data["size"],
            "content": content,
            "html_url": data["html_url"],
        }

    async def _list_issues(self, client: httpx.AsyncClient, headers: dict, params: dict) -> list:
        """List repository issues."""
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required for list_issues")

        per_page = min(params.get("per_page", 20), 100)
        state = params.get("state", "open")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/issues",
            headers=headers,
            params={"per_page": per_page, "state": state},
            timeout=30,
        )
        response.raise_for_status()
        issues = response.json()
        # Filter out pull requests (they appear in issues endpoint)
        return [
            {
                "number": i["number"],
                "title": i["title"],
                "state": i["state"],
                "author": i["user"]["login"],
                "labels": [l["name"] for l in i.get("labels", [])],
                "created_at": i["created_at"],
                "html_url": i["html_url"],
            }
            for i in issues
            if "pull_request" not in i
        ]

    async def _get_issue(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Get issue details."""
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")
        if not owner or not repo or not issue_number:
            raise ValueError("owner, repo, and issue_number are required for get_issue")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/issues/{issue_number}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        i = response.json()
        return {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "body": i.get("body", ""),
            "author": i["user"]["login"],
            "labels": [l["name"] for l in i.get("labels", [])],
            "assignees": [a["login"] for a in i.get("assignees", [])],
            "created_at": i["created_at"],
            "updated_at": i["updated_at"],
            "html_url": i["html_url"],
            "comments": i["comments"],
        }

    async def _create_issue(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Create a new issue."""
        owner = params.get("owner")
        repo = params.get("repo")
        title = params.get("title")
        body = params.get("body")
        if not owner or not repo or not title:
            raise ValueError("owner, repo, and title are required for create_issue")

        payload = {
            "title": title,
            "body": body or "",
        }

        # Add optional fields
        if params.get("labels"):
            payload["labels"] = params["labels"]
        if params.get("assignees"):
            payload["assignees"] = params["assignees"]

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/issues",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        issue = response.json()
        return {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "body": issue.get("body", ""),
            "author": issue["user"]["login"],
            "labels": [l["name"] for l in issue.get("labels", [])],
            "html_url": issue["html_url"],
            "created_at": issue["created_at"],
        }

    async def _create_issue_comment(
        self, client: httpx.AsyncClient, headers: dict, params: dict
    ) -> dict:
        """Create a comment on an issue."""
        owner = params.get("owner")
        repo = params.get("repo")
        issue_number = params.get("issue_number")
        body = params.get("body")
        if not owner or not repo or not issue_number or not body:
            raise ValueError(
                "owner, repo, issue_number, and body are required for create_issue_comment"
            )

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers=headers,
            json={"body": body},
            timeout=30,
        )
        response.raise_for_status()
        comment = response.json()
        return {
            "id": comment["id"],
            "body": comment["body"],
            "author": comment["user"]["login"],
            "created_at": comment["created_at"],
            "html_url": comment["html_url"],
        }

    async def _list_prs(self, client: httpx.AsyncClient, headers: dict, params: dict) -> list:
        """List pull requests."""
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required for list_prs")

        per_page = min(params.get("per_page", 20), 100)
        state = params.get("state", "open")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/pulls",
            headers=headers,
            params={"per_page": per_page, "state": state},
            timeout=30,
        )
        response.raise_for_status()
        prs = response.json()
        return [
            {
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "author": pr["user"]["login"],
                "head": pr["head"]["ref"],
                "base": pr["base"]["ref"],
                "created_at": pr["created_at"],
                "html_url": pr["html_url"],
            }
            for pr in prs
        ]

    async def _get_pr(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Get pull request details."""
        owner = params.get("owner")
        repo = params.get("repo")
        pr_number = params.get("pr_number")
        if not owner or not repo or not pr_number:
            raise ValueError("owner, repo, and pr_number are required for get_pr")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        pr = response.json()
        return {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "body": pr.get("body", ""),
            "author": pr["user"]["login"],
            "head": pr["head"]["ref"],
            "base": pr["base"]["ref"],
            "mergeable": pr.get("mergeable"),
            "additions": pr["additions"],
            "deletions": pr["deletions"],
            "changed_files": pr["changed_files"],
            "commits": pr["commits"],
            "created_at": pr["created_at"],
            "updated_at": pr["updated_at"],
            "html_url": pr["html_url"],
        }

    async def _create_pr(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Create a new pull request."""
        owner = params.get("owner")
        repo = params.get("repo")
        title = params.get("title")
        head = params.get("head")
        base = params.get("base")
        body = params.get("body")

        if not owner or not repo or not title or not head or not base:
            raise ValueError("owner, repo, title, head, and base are required for create_pr")

        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body or "",
        }

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/pulls",
            headers=headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        pr = response.json()
        return {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "body": pr.get("body", ""),
            "author": pr["user"]["login"],
            "head": pr["head"]["ref"],
            "base": pr["base"]["ref"],
            "html_url": pr["html_url"],
            "created_at": pr["created_at"],
        }

    async def _create_pr_comment(
        self, client: httpx.AsyncClient, headers: dict, params: dict
    ) -> dict:
        """Create a comment on a pull request."""
        owner = params.get("owner")
        repo = params.get("repo")
        pr_number = params.get("pr_number")
        body = params.get("body")
        if not owner or not repo or not pr_number or not body:
            raise ValueError("owner, repo, pr_number, and body are required for create_pr_comment")

        # PR comments use the issues endpoint
        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=headers,
            json={"body": body},
            timeout=30,
        )
        response.raise_for_status()
        comment = response.json()
        return {
            "id": comment["id"],
            "body": comment["body"],
            "author": comment["user"]["login"],
            "created_at": comment["created_at"],
            "html_url": comment["html_url"],
        }

    async def _create_pr_review(
        self, client: httpx.AsyncClient, headers: dict, params: dict
    ) -> dict:
        """Create a review on a pull request."""
        owner = params.get("owner")
        repo = params.get("repo")
        pr_number = params.get("pr_number")
        body = params.get("body")
        event = params.get("event", "COMMENT")  # APPROVE, REQUEST_CHANGES, or COMMENT

        if not owner or not repo or not pr_number or not body:
            raise ValueError("owner, repo, pr_number, and body are required for create_pr_review")

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
            json={"body": body, "event": event},
            timeout=30,
        )
        response.raise_for_status()
        review = response.json()
        return {
            "id": review["id"],
            "state": review["state"],
            "body": review.get("body", ""),
            "author": review["user"]["login"],
            "submitted_at": review.get("submitted_at"),
            "html_url": review["html_url"],
        }

    async def _create_commit(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Create a commit with file changes using the Git Data API."""
        owner = params.get("owner")
        repo = params.get("repo")
        branch = params.get("branch")
        message = params.get("message")
        files = params.get("files", [])

        if not owner or not repo or not branch or not message or not files:
            raise ValueError(
                "owner, repo, branch, message, and files are required for create_commit"
            )

        # Get the reference (branch)
        ref_response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/git/ref/heads/{branch}",
            headers=headers,
            timeout=30,
        )
        ref_response.raise_for_status()
        ref_data = ref_response.json()
        base_sha = ref_data["object"]["sha"]

        # Get the base commit
        commit_response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/git/commits/{base_sha}",
            headers=headers,
            timeout=30,
        )
        commit_response.raise_for_status()
        commit_data = commit_response.json()
        base_tree_sha = commit_data["tree"]["sha"]

        # Create blobs for each file
        tree_items = []
        for file in files:
            path = file.get("path")
            content = file.get("content")
            mode = file.get("mode", "100644")  # Default to regular file

            if not path or content is None:
                continue

            # Create blob
            blob_response = await client.post(
                f"{self._base_url}/repos/{owner}/{repo}/git/blobs",
                headers=headers,
                json={"content": content, "encoding": "utf-8"},
                timeout=30,
            )
            blob_response.raise_for_status()
            blob_sha = blob_response.json()["sha"]

            tree_items.append(
                {
                    "path": path,
                    "mode": mode,
                    "type": "blob",
                    "sha": blob_sha,
                }
            )

        # Create tree
        tree_response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/git/trees",
            headers=headers,
            json={"base_tree": base_tree_sha, "tree": tree_items},
            timeout=30,
        )
        tree_response.raise_for_status()
        tree_sha = tree_response.json()["sha"]

        # Create commit
        commit_payload = {
            "message": message,
            "tree": tree_sha,
            "parents": [base_sha],
        }

        # Add author info if provided
        if params.get("author_name") and params.get("author_email"):
            commit_payload["author"] = {
                "name": params["author_name"],
                "email": params["author_email"],
            }

        new_commit_response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/git/commits",
            headers=headers,
            json=commit_payload,
            timeout=30,
        )
        new_commit_response.raise_for_status()
        new_commit_data = new_commit_response.json()
        new_commit_sha = new_commit_data["sha"]

        # Update reference
        update_ref_response = await client.patch(
            f"{self._base_url}/repos/{owner}/{repo}/git/refs/heads/{branch}",
            headers=headers,
            json={"sha": new_commit_sha},
            timeout=30,
        )
        update_ref_response.raise_for_status()

        return {
            "sha": new_commit_sha[:7],
            "message": message,
            "author": new_commit_data["author"]["name"],
            "date": new_commit_data["author"]["date"],
            "html_url": new_commit_data["html_url"],
            "files_changed": len(tree_items),
        }

    async def _search_code(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Search code in repositories."""
        query = params.get("query")
        if not query:
            raise ValueError("query is required for search_code")

        per_page = min(params.get("per_page", 20), 100)

        response = await client.get(
            f"{self._base_url}/search/code",
            headers=headers,
            params={"q": query, "per_page": per_page},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return {
            "total_count": data["total_count"],
            "items": [
                {
                    "name": item["name"],
                    "path": item["path"],
                    "repository": item["repository"]["full_name"],
                    "html_url": item["html_url"],
                }
                for item in data["items"]
            ],
        }

    async def _list_branches(self, client: httpx.AsyncClient, headers: dict, params: dict) -> list:
        """List repository branches."""
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required for list_branches")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/branches",
            headers=headers,
            params={"per_page": 100},
            timeout=30,
        )
        response.raise_for_status()
        branches = response.json()
        return [
            {
                "name": b["name"],
                "protected": b["protected"],
            }
            for b in branches
        ]

    async def _create_branch(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Create a new branch from an existing branch."""
        owner = params.get("owner")
        repo = params.get("repo")
        new_branch = params.get("branch")
        from_branch = params.get("from_branch")

        if not owner or not repo:
            raise ValueError("owner and repo are required for create_branch")
        if not new_branch:
            raise ValueError("branch is required for create_branch")

        # If no source branch specified, get the default branch from repo info
        if not from_branch:
            repo_response = await client.get(
                f"{self._base_url}/repos/{owner}/{repo}",
                headers=headers,
                timeout=30,
            )
            repo_response.raise_for_status()
            repo_data = repo_response.json()
            from_branch = repo_data.get("default_branch", "main")

        # Get the SHA of the source branch
        ref_response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
            headers=headers,
            timeout=30,
        )
        ref_response.raise_for_status()
        source_sha = ref_response.json()["object"]["sha"]

        # Create the new branch reference
        create_ref_response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/git/refs",
            headers=headers,
            json={
                "ref": f"refs/heads/{new_branch}",
                "sha": source_sha,
            },
            timeout=30,
        )
        create_ref_response.raise_for_status()

        return {
            "branch": new_branch,
            "from_branch": from_branch,
            "sha": source_sha[:7],
            "repository": f"{owner}/{repo}",
            "url": f"https://github.com/{owner}/{repo}/tree/{new_branch}",
        }

    async def _get_readme(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        """Get repository README."""
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required for get_readme")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/readme",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        # Decode content
        import base64

        content = base64.b64decode(data["content"]).decode("utf-8")

        return {
            "name": data["name"],
            "path": data["path"],
            "content": content,
            "html_url": data["html_url"],
        }
