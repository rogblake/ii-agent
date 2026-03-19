import io
import json
import tarfile
from typing import Any, Dict, Optional

import httpx
from ii_agent.agent.runtime.agents.agent import IIAgent
from ii_agent.agent.sandboxes.base import SandboxManager
from ii_agent.agent.runtime.tools.function import FunctionCall
from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool
from ii_agent.agent.runtime.tools import ToolResult
from ii_agent.core.logger import logger

class GitHubAgentTool(BaseSandboxTool):
    def __init__(
        self,
        github_token: str,
        workspace_path: str = "/workspace",
        github_metadata: Optional[Dict[str, Any]] = None,
        default_repository: Optional[Dict[str, str]] = None,
    ):
        """Initialize GitHub tool.

        Args:
            github_token: GitHub OAuth access token
            workspace_path: Workspace path in sandbox (e.g. "/workspace")
            github_metadata: User metadata from GitHub (login, email, etc.)
            default_repository: Default repo context (owner, name, full_name, default_branch)
        """
        self.github_token = github_token
        self.workspace_path = workspace_path
        self.github_metadata = github_metadata or {}
        self.default_repository = default_repository
        self._base_url = "https://api.github.com"
        self.sandbox: SandboxManager = None
        # Build description
        base_desc = "Access GitHub repositories to perform various operations. "

        if self.default_repository:
            base_desc += (
                f"\n\nDEFAULT REPOSITORY: {self.default_repository.get('full_name', 'N/A')} "
                f"(branch: {self.default_repository.get('default_branch', 'main')}). "
                "When owner/repo are not specified, this repository will be used automatically.\n\n"
            )

        base_desc += (
            "Available actions:\n"
            "- list_repos: List user's accessible repositories\n"
            "- get_repo: Get repository details\n"
            "- list_commits: List recent commits (optional: branch, per_page)\n"
            "- get_file: Get file content (requires: path; optional: branch)\n"
            "- list_issues: List repository issues (optional: state, per_page)\n"
            "- get_issue: Get issue details (requires: issue_number)\n"
            "- create_issue: Create a new issue (requires: title, body; optional: labels, assignees)\n"
            "- create_issue_comment: Add comment to issue (requires: issue_number, body)\n"
            "- list_prs: List pull requests (optional: state, per_page)\n"
            "- get_pr: Get pull request details (requires: pr_number)\n"
            "- create_pr: Create pull request (requires: title, head, base, body)\n"
            "- create_pr_comment: Add comment to PR (requires: pr_number, body)\n"
            "- create_pr_review: Create PR review (requires: pr_number, body; optional: event)\n"
            "- create_commit: Create commit with file changes (requires: branch, message, files)\n"
            "- search_code: Search code in repositories (requires: query; optional: per_page)\n"
            "- list_branches: List repository branches\n"
            "- create_branch: Create a new branch (requires: branch; optional: from_branch)\n"
            "- get_readme: Get repository README\n"
            "- clone_repo: Clone repository to workspace (optional: branch, path)"
        )

        self.name = "github"
        self.description = base_desc
        self.display_name = "GitHub"
        self.read_only = False
        self.input_schema = {
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
                        "clone_repo",
                    ],
                },
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "path": {"type": "string", "description": "File path in repository"},
                "branch": {"type": "string", "description": "Branch name"},
                "issue_number": {"type": "integer", "description": "Issue number"},
                "pr_number": {"type": "integer", "description": "Pull request number"},
                "title": {"type": "string", "description": "Title for issue/PR"},
                "body": {"type": "string", "description": "Body/description text"},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Issue/PR state filter",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Results per page (max 100)",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels for issue",
                },
                "assignees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Assignees for issue",
                },
                "head": {"type": "string", "description": "Head branch for PR"},
                "base": {"type": "string", "description": "Base branch for PR"},
                "event": {
                    "type": "string",
                    "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                    "description": "PR review event type",
                },
                "message": {"type": "string", "description": "Commit message"},
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                    "description": "Files to commit",
                },
                "author_name": {"type": "string", "description": "Commit author name"},
                "author_email": {"type": "string", "description": "Commit author email"},
                "query": {"type": "string", "description": "Search query"},
                "from_branch": {
                    "type": "string",
                    "description": "Source branch to create new branch from (defaults to default branch)",
                },
            },
            "required": ["action"],
        }

    async def on_tool_start(self, agent: IIAgent, fc: FunctionCall) -> None:
        await super().on_tool_start(agent, fc)
        self.sandbox = agent.sandbox

    def _get_repo_context(self, tool_input: Dict[str, Any]) -> tuple[str, str]:
        """Get owner and repo from input or default repository.

        Returns:
            Tuple of (owner, repo)

        Raises:
            ValueError: If no repository context available
        """
        owner = tool_input.get("owner")
        repo = tool_input.get("repo")

        if not owner or not repo:
            if self.default_repository:
                owner = owner or self.default_repository.get("owner")
                repo = repo or self.default_repository.get("name")
            else:
                raise ValueError("No repository specified and no default repository set")

        return owner, repo

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute GitHub action.

        Args:
            tool_input: Tool input parameters

        Returns:
            ToolResult with GitHub API response
        """
        action = tool_input.get("action")
        if not action:
            return ToolResult(
                llm_content="Error: 'action' parameter is required",
                is_error=True,
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }

                # Route to appropriate handler
                if action == "list_repos":
                    result = await self._list_repos(client, headers, tool_input)
                elif action == "get_repo":
                    result = await self._get_repo(client, headers, tool_input)
                elif action == "list_commits":
                    result = await self._list_commits(client, headers, tool_input)
                elif action == "get_file":
                    result = await self._get_file(client, headers, tool_input)
                elif action == "list_issues":
                    result = await self._list_issues(client, headers, tool_input)
                elif action == "get_issue":
                    result = await self._get_issue(client, headers, tool_input)
                elif action == "create_issue":
                    result = await self._create_issue(client, headers, tool_input)
                elif action == "create_issue_comment":
                    result = await self._create_issue_comment(client, headers, tool_input)
                elif action == "list_prs":
                    result = await self._list_prs(client, headers, tool_input)
                elif action == "get_pr":
                    result = await self._get_pr(client, headers, tool_input)
                elif action == "create_pr":
                    result = await self._create_pr(client, headers, tool_input)
                elif action == "create_pr_comment":
                    result = await self._create_pr_comment(client, headers, tool_input)
                elif action == "create_pr_review":
                    result = await self._create_pr_review(client, headers, tool_input)
                elif action == "create_commit":
                    result = await self._create_commit(client, headers, tool_input)
                elif action == "search_code":
                    result = await self._search_code(client, headers, tool_input)
                elif action == "list_branches":
                    result = await self._list_branches(client, headers, tool_input)
                elif action == "create_branch":
                    result = await self._create_branch(client, headers, tool_input)
                elif action == "get_readme":
                    result = await self._get_readme(client, headers, tool_input)
                elif action == "clone_repo":
                    result = await self._clone_repo(tool_input)
                else:
                    return ToolResult(
                        llm_content=f"Error: Unknown action '{action}'",
                        is_error=True,
                    )

                return ToolResult(llm_content=result)

        except httpx.HTTPStatusError as e:
            error_msg = f"GitHub API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            return ToolResult(llm_content=error_msg, is_error=True)
        except Exception as e:
            error_msg = f"Error executing GitHub action '{action}': {str(e)}"
            logger.error(error_msg)
            return ToolResult(llm_content=error_msg, is_error=True)

    # Action handlers (simplified versions - implement full logic as needed)
    async def _list_repos(self, client, headers, params):
        """List user's repositories."""
        per_page = params.get("per_page", 30)
        response = await client.get(
            f"{self._base_url}/user/repos",
            headers=headers,
            params={"per_page": per_page, "sort": "updated"},
        )
        response.raise_for_status()
        repos = response.json()
        return f"Found {len(repos)} repositories:\n" + "\n".join(
            [f"- {r['full_name']} ({r['html_url']})" for r in repos[:20]]
        )

    async def _get_repo(self, client, headers, params):
        """Get repository details."""
        owner, repo = self._get_repo_context(params)
        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        return json.dumps(data, indent=2)

    async def _list_commits(self, client, headers, params):
        """List repository commits."""
        owner, repo = self._get_repo_context(params)
        url_params = {"per_page": params.get("per_page", 10)}
        if params.get("branch"):
            url_params["sha"] = params["branch"]

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/commits",
            headers=headers,
            params=url_params,
        )
        response.raise_for_status()
        commits = response.json()
        return "Recent commits:\n" + "\n".join(
            [
                f"- {c['sha'][:7]}: {c['commit']['message'].split(chr(10))[0]} by {c['commit']['author']['name']}"
                for c in commits
            ]
        )

    async def _get_file(self, client, headers, params):
        """Get file content from repository."""
        owner, repo = self._get_repo_context(params)
        path = params.get("path")
        if not path:
            raise ValueError("'path' parameter is required for get_file action")

        url_params = {}
        if params.get("branch"):
            url_params["ref"] = params["branch"]

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/contents/{path}",
            headers=headers,
            params=url_params,
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return f"Path '{path}' is a directory with {len(data)} items"

        import base64

        content = base64.b64decode(data["content"]).decode("utf-8")
        return f"File: {path}\n\n{content}"

    async def _list_issues(self, client, headers, params):
        """List repository issues."""
        owner, repo = self._get_repo_context(params)
        url_params = {
            "state": params.get("state", "open"),
            "per_page": params.get("per_page", 10),
        }

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/issues",
            headers=headers,
            params=url_params,
        )
        response.raise_for_status()
        issues = response.json()
        return "Issues:\n" + "\n".join(
            [f"- #{i['number']}: {i['title']} ({i['state']})" for i in issues]
        )

    async def _get_issue(self, client, headers, params):
        """Get issue details."""
        owner, repo = self._get_repo_context(params)
        issue_number = params.get("issue_number")
        if not issue_number:
            raise ValueError("'issue_number' is required")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/issues/{issue_number}",
            headers=headers,
        )
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)

    async def _create_issue(self, client, headers, params):
        """Create a new issue."""
        owner, repo = self._get_repo_context(params)
        data = {
            "title": params.get("title"),
            "body": params.get("body"),
        }
        if params.get("labels"):
            data["labels"] = params["labels"]
        if params.get("assignees"):
            data["assignees"] = params["assignees"]

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/issues",
            headers=headers,
            json=data,
        )
        response.raise_for_status()
        issue = response.json()
        return f"Created issue #{issue['number']}: {issue['html_url']}"

    async def _create_issue_comment(self, client, headers, params):
        """Add comment to an issue."""
        owner, repo = self._get_repo_context(params)
        issue_number = params.get("issue_number")
        body = params.get("body")

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers=headers,
            json={"body": body},
        )
        response.raise_for_status()
        return f"Comment added to issue #{issue_number}"

    async def _list_prs(self, client, headers, params):
        """List pull requests."""
        owner, repo = self._get_repo_context(params)
        url_params = {
            "state": params.get("state", "open"),
            "per_page": params.get("per_page", 10),
        }

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/pulls",
            headers=headers,
            params=url_params,
        )
        response.raise_for_status()
        prs = response.json()
        return "Pull Requests:\n" + "\n".join(
            [f"- #{pr['number']}: {pr['title']} ({pr['state']})" for pr in prs]
        )

    async def _get_pr(self, client, headers, params):
        """Get pull request details."""
        owner, repo = self._get_repo_context(params)
        pr_number = params.get("pr_number")

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)

    async def _create_pr(self, client, headers, params):
        """Create a pull request."""
        owner, repo = self._get_repo_context(params)
        data = {
            "title": params.get("title"),
            "head": params.get("head"),
            "base": params.get("base"),
            "body": params.get("body"),
        }

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/pulls",
            headers=headers,
            json=data,
        )
        response.raise_for_status()
        pr = response.json()
        return f"Created PR #{pr['number']}: {pr['html_url']}"

    async def _create_pr_comment(self, client, headers, params):
        """Add comment to a PR."""
        owner, repo = self._get_repo_context(params)
        pr_number = params.get("pr_number")
        body = params.get("body")

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=headers,
            json={"body": body},
        )
        response.raise_for_status()
        return f"Comment added to PR #{pr_number}"

    async def _create_pr_review(self, client, headers, params):
        """Create a PR review."""
        owner, repo = self._get_repo_context(params)
        pr_number = params.get("pr_number")
        data = {
            "body": params.get("body"),
            "event": params.get("event", "COMMENT"),
        }

        response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
            json=data,
        )
        response.raise_for_status()
        return f"Review added to PR #{pr_number}"

    async def _create_commit(self, client, headers, params):
        """Create a commit with file changes using GitHub's Git Data API.

        This method creates commits by:
        1. Getting the current commit SHA from the branch
        2. Creating blobs for each file
        3. Creating a new tree with the file changes
        4. Creating a new commit pointing to that tree
        5. Updating the branch reference to point to the new commit

        Required params:
            - branch: The branch to commit to
            - message: Commit message
            - files: List of {path, content} objects

        Optional params:
            - author_name: Commit author name (defaults to GitHub user)
            - author_email: Commit author email (defaults to GitHub user email)
        """
        import base64

        owner, repo = self._get_repo_context(params)
        branch = params.get("branch")
        message = params.get("message")
        files = params.get("files", [])

        if not branch:
            raise ValueError("'branch' is required for create_commit")
        if not message:
            raise ValueError("'message' is required for create_commit")
        if not files:
            raise ValueError("'files' is required for create_commit (list of {path, content})")

        # Validate files structure
        for f in files:
            if not isinstance(f, dict) or "path" not in f or "content" not in f:
                raise ValueError("Each file must have 'path' and 'content' fields")

        # Step 1: Get the current commit SHA from the branch
        ref_response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/git/refs/heads/{branch}",
            headers=headers,
        )
        ref_response.raise_for_status()
        ref_data = ref_response.json()
        current_commit_sha = ref_data["object"]["sha"]

        # Step 2: Get the current commit to find its tree SHA
        commit_response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/git/commits/{current_commit_sha}",
            headers=headers,
        )
        commit_response.raise_for_status()
        commit_data = commit_response.json()
        base_tree_sha = commit_data["tree"]["sha"]

        # Step 3: Create blobs for each file and build tree entries
        tree_entries = []
        for file_info in files:
            file_path = file_info["path"]
            file_content = file_info["content"]

            # Create a blob for the file content
            blob_response = await client.post(
                f"{self._base_url}/repos/{owner}/{repo}/git/blobs",
                headers=headers,
                json={
                    "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8"),
                    "encoding": "base64",
                },
            )
            blob_response.raise_for_status()
            blob_sha = blob_response.json()["sha"]

            tree_entries.append(
                {
                    "path": file_path,
                    "mode": "100644",  # Regular file
                    "type": "blob",
                    "sha": blob_sha,
                }
            )

        # Step 4: Create a new tree with the changes
        tree_response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/git/trees",
            headers=headers,
            json={
                "base_tree": base_tree_sha,
                "tree": tree_entries,
            },
        )
        tree_response.raise_for_status()
        new_tree_sha = tree_response.json()["sha"]

        # Step 5: Create the commit
        commit_payload = {
            "message": message,
            "tree": new_tree_sha,
            "parents": [current_commit_sha],
        }

        # Add author info if provided
        author_name = params.get("author_name") or self.github_metadata.get("name")
        author_email = params.get("author_email") or self.github_metadata.get("email")
        if author_name and author_email:
            commit_payload["author"] = {
                "name": author_name,
                "email": author_email,
            }

        new_commit_response = await client.post(
            f"{self._base_url}/repos/{owner}/{repo}/git/commits",
            headers=headers,
            json=commit_payload,
        )
        new_commit_response.raise_for_status()
        new_commit_data = new_commit_response.json()
        new_commit_sha = new_commit_data["sha"]

        # Step 6: Update the branch reference to point to the new commit
        update_ref_response = await client.patch(
            f"{self._base_url}/repos/{owner}/{repo}/git/refs/heads/{branch}",
            headers=headers,
            json={"sha": new_commit_sha},
        )
        update_ref_response.raise_for_status()

        files_list = ", ".join([f["path"] for f in files])
        return (
            f"Successfully created commit on {owner}/{repo}:{branch}\n"
            f"Commit SHA: {new_commit_sha[:7]}\n"
            f"Message: {message}\n"
            f"Files changed: {files_list}\n"
            f"URL: https://github.com/{owner}/{repo}/commit/{new_commit_sha}"
        )

    async def _search_code(self, client, headers, params):
        """Search code across repositories."""
        query = params.get("query")
        if not query:
            raise ValueError("'query' is required for search_code")

        response = await client.get(
            f"{self._base_url}/search/code",
            headers=headers,
            params={"q": query, "per_page": params.get("per_page", 10)},
        )
        response.raise_for_status()
        results = response.json()
        items = results.get("items", [])
        return f"Found {results['total_count']} results:\n" + "\n".join(
            [f"- {item['repository']['full_name']}: {item['path']}" for item in items[:10]]
        )

    async def _list_branches(self, client, headers, params):
        """List repository branches."""
        owner, repo = self._get_repo_context(params)

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/branches",
            headers=headers,
        )
        response.raise_for_status()
        branches = response.json()
        return "Branches:\n" + "\n".join([f"- {b['name']}" for b in branches])

    async def _create_branch(self, client, headers, params):
        """Create a new branch from an existing branch.

        Required params:
            - branch: Name of the new branch to create

        Optional params:
            - from_branch: Source branch to create from (defaults to repo's default branch)
        """
        owner, repo = self._get_repo_context(params)
        new_branch = params.get("branch")
        from_branch = params.get("from_branch")

        if not new_branch:
            raise ValueError("'branch' is required for create_branch")

        # If no source branch specified, get the default branch from repo info
        if not from_branch:
            repo_response = await client.get(
                f"{self._base_url}/repos/{owner}/{repo}",
                headers=headers,
            )
            repo_response.raise_for_status()
            repo_data = repo_response.json()
            from_branch = repo_data.get("default_branch", "main")

        # Get the SHA of the source branch
        ref_response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/git/refs/heads/{from_branch}",
            headers=headers,
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
        )
        create_ref_response.raise_for_status()

        return (
            f"Successfully created branch '{new_branch}' from '{from_branch}'\n"
            f"Repository: {owner}/{repo}\n"
            f"SHA: {source_sha[:7]}\n"
            f"URL: https://github.com/{owner}/{repo}/tree/{new_branch}"
        )

    async def _get_readme(self, client, headers, params):
        """Get repository README."""
        owner, repo = self._get_repo_context(params)

        response = await client.get(
            f"{self._base_url}/repos/{owner}/{repo}/readme",
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        import base64

        content = base64.b64decode(data["content"]).decode("utf-8")
        return f"README for {owner}/{repo}:\n\n{content}"

    async def _clone_repo(self, params):
        """Clone repository to workspace using git clone with token authentication."""
        import traceback

        owner, repo = self._get_repo_context(params)
        branch = params.get("branch")

        target_path = params.get("path", f"{self.workspace_path}/{repo}")
        current_step = "initialization"

        try:
            current_step = "fetching repo info"
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                headers = {
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }

                # If no branch specified, get the default branch from repo info
                if not branch:
                    repo_response = await client.get(
                        f"{self._base_url}/repos/{owner}/{repo}",
                        headers=headers,
                    )
                    repo_response.raise_for_status()
                    repo_data = repo_response.json()
                    branch = repo_data.get("default_branch", "main")

            # Try git clone first (more reliable for private repos)
            current_step = f"cloning repository with git for branch '{branch}'"
            clone_url = f"https://x-access-token:{self.github_token}@github.com/{owner}/{repo}.git"

            try:
                # Create parent directory if needed
                parent_dir = "/".join(target_path.split("/")[:-1])
                if parent_dir:
                    await self.sandbox.run_command(f"mkdir -p {parent_dir}", user="root")

                # Clone with depth 1 for faster cloning, specific branch
                clone_cmd = f"git clone --depth 1 --branch {branch} {clone_url} {target_path}"
                await self.sandbox.run_command(clone_cmd, timeout=300, user="root")

                # Remove .git directory to save space and avoid token exposure
                await self.sandbox.run_command(f"rm -rf {target_path}/.git", user="root")

                # Change ownership to pn user
                await self.sandbox.run_command(f"sudo chown -R pn:pn {target_path}", user="root")

                # List files to report
                try:
                    ls_result = await self.sandbox.run_command(
                        f"find {target_path} -type f | head -20", user="root"
                    )
                    files_output = ls_result if ls_result else "Files cloned successfully"
                except Exception:
                    files_output = "Files cloned successfully (unable to list)"

                return (
                    f"Successfully cloned {owner}/{repo} to {target_path}\n"
                    f"Branch: {branch}\n\n"
                    f"Files:\n{files_output}"
                )
            except Exception as git_err:
                logger.warning(f"Git clone failed: {git_err}, falling back to tarball method")

            # Fallback to tarball method
            current_step = f"downloading tarball for branch '{branch}'"
            tarball_url = f"{self._base_url}/repos/{owner}/{repo}/tarball/{branch}"
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                headers = {
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
                response = await client.get(tarball_url, headers=headers)
                response.raise_for_status()
                tarball_content = response.content
                tarball_size = len(tarball_content)

            logger.info(f"Downloaded tarball: {tarball_size} bytes for {owner}/{repo}@{branch}")

            # Create target directory using dedicated method
            current_step = f"creating target directory: {target_path}"
            logger.info(f"Creating target directory: {target_path}")
            try:
                await self.sandbox.create_directory(target_path, exist_ok=True)
                logger.info(f"Created target directory: {target_path}")
            except Exception as e:
                raise RuntimeError(f"Failed to create directory: {type(e).__name__}: {str(e)}")

            # Try fast method first: upload tarball and extract with run_command
            current_step = "uploading and extracting tarball"
            tarball_path = f"/tmp/{repo}_{branch}.tar.gz"
            extraction_success = False

            try:
                logger.info(f"Uploading tarball to {tarball_path}...")
                await self.sandbox.write_file(tarball_path, tarball_content)
                logger.info("Tarball uploaded, attempting extraction...")

                # Try to extract using run_command
                extract_cmd = f"tar -xzf {tarball_path} -C {target_path} --strip-components=1"
                await self.sandbox.run_command(extract_cmd, user="root")
                logger.info("Tarball extracted successfully using run_command")

                # Change ownership to pn user
                await self.sandbox.run_command(f"sudo chown -R pn:pn {target_path}", user="root")

                # Clean up tarball
                try:
                    await self.sandbox.run_command(f"rm -f {tarball_path}", user="root")
                except Exception:
                    pass

                extraction_success = True

                # List files to report
                try:
                    ls_result = await self.sandbox.run_command(
                        f"find {target_path} -type f | head -20", user="root"
                    )
                    files_output = ls_result if ls_result else "Files extracted successfully"
                except Exception:
                    files_output = "Files extracted successfully (unable to list)"

            except Exception as extract_err:
                logger.warning(
                    f"Fast extraction failed: {extract_err}, falling back to file-by-file upload"
                )

            # Fallback: extract in memory and upload files individually
            if not extraction_success:
                current_step = "extracting and uploading files (fallback)"
                logger.info("Starting fallback: extract tarball and upload files individually...")
                try:
                    tar_buffer = io.BytesIO(tarball_content)
                    uploaded_files = []
                    created_dirs = set()

                    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
                        members = tar.getmembers()
                        logger.info(f"Tarball contains {len(members)} members")

                        # Find the top-level directory to strip
                        top_level_dir = None
                        for member in members:
                            if "/" in member.name:
                                top_level_dir = member.name.split("/")[0]
                                break

                        # First pass: collect all files
                        files_to_upload = []
                        for member in members:
                            if member.name == top_level_dir:
                                continue
                            if top_level_dir and member.name.startswith(top_level_dir + "/"):
                                relative_path = member.name[len(top_level_dir) + 1 :]
                            else:
                                relative_path = member.name
                            if not relative_path:
                                continue
                            full_path = f"{target_path}/{relative_path}"
                            if member.isfile():
                                file_obj = tar.extractfile(member)
                                if file_obj:
                                    content = file_obj.read()
                                    files_to_upload.append((full_path, relative_path, content))

                        logger.info(f"Found {len(files_to_upload)} files to upload")

                        # Upload files
                        for i, (full_path, relative_path, content) in enumerate(files_to_upload):
                            parent_dir = "/".join(full_path.split("/")[:-1])
                            if parent_dir and parent_dir not in created_dirs:
                                try:
                                    await self.sandbox.create_directory(parent_dir, exist_ok=True)
                                    created_dirs.add(parent_dir)
                                except Exception:
                                    pass
                            try:
                                await self.sandbox.write_file(full_path, content)
                                uploaded_files.append(relative_path)
                                if (i + 1) % 20 == 0:
                                    logger.info(f"Uploaded {i + 1}/{len(files_to_upload)} files...")
                            except Exception as file_err:
                                logger.warning(f"Failed to upload {relative_path}: {file_err}")

                    logger.info(f"Uploaded {len(uploaded_files)} files to {target_path}")

                    # Change ownership to pn user
                    await self.sandbox.run_command(f"chown -R pn:pn {target_path}", user="root")

                    files_output = "\n".join(uploaded_files[:20])
                    if len(uploaded_files) > 20:
                        files_output += f"\n... and {len(uploaded_files) - 20} more files"
                except Exception as e:
                    raise RuntimeError(
                        f"Failed to extract/upload files: {type(e).__name__}: {str(e)}"
                    )

            return (
                f"Successfully cloned {owner}/{repo} to {target_path}\n"
                f"Branch: {branch}\n\n"
                f"Files:\n{files_output}"
            )

        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.text
            except Exception:
                pass
            error_msg = f"GitHub API error at step '{current_step}': {e.response.status_code} - {error_body}"
            logger.error(error_msg)
            raise RuntimeError(f"Clone failed: {error_msg}")
        except RuntimeError:
            raise
        except Exception as e:
            error_msg = str(e).replace(self.github_token, "***")
            tb = traceback.format_exc().replace(self.github_token, "***")
            full_error = f"Clone failed at step '{current_step}': {type(e).__name__}: {error_msg}\nTraceback:\n{tb}"
            logger.error(full_error)
            raise RuntimeError(full_error)
