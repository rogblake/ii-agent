"""GitHub skill download service.

Downloads skill folders from GitHub URLs and parses SKILL.md metadata.
Supports URLs in the format: https://github.com/{owner}/{repo}/tree/{branch}/{path}
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

import httpx

from ii_agent.agents.skills.skills_ref.errors import ParseError, ValidationError
from ii_agent.agents.skills.skills_ref.models import SkillProperties
from ii_agent.agents.skills.skills_ref.parser import parse_frontmatter
from ii_agent.core.logger import logger

# Maximum length for sanitized skill names
MAX_SKILL_NAME_LENGTH = 64


def sanitize_skill_name(name: str) -> str:
    """Sanitize a skill name to prevent path traversal and ensure safe filesystem usage.

    This function converts the input name to a safe slug that:
    - Contains only lowercase alphanumeric characters and hyphens
    - Has no path traversal characters (../, /, \\, etc.)
    - Is non-empty and reasonably sized

    Args:
        name: Raw skill name from SKILL.md

    Returns:
        Sanitized skill name (slug)

    Raises:
        ValidationError: If the name cannot be sanitized to a valid slug
    """
    if not name or not isinstance(name, str):
        raise ValidationError("Skill name must be a non-empty string")

    # Normalize unicode characters
    normalized = unicodedata.normalize("NFKD", name)
    # Remove non-ASCII characters
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase
    lowered = ascii_only.lower()

    # Replace spaces and underscores with hyphens
    with_hyphens = re.sub(r"[\s_]+", "-", lowered)

    # Remove any characters that are not alphanumeric or hyphens
    # This removes path traversal chars like . / \ and other special chars
    safe_chars = re.sub(r"[^a-z0-9-]", "", with_hyphens)

    # Collapse multiple hyphens into one
    collapsed = re.sub(r"-+", "-", safe_chars)

    # Strip leading/trailing hyphens
    stripped = collapsed.strip("-")

    # Truncate to max length
    truncated = stripped[:MAX_SKILL_NAME_LENGTH]

    # Final validation
    if not truncated:
        raise ValidationError(
            f"Skill name '{name}' cannot be converted to a valid slug. "
            "Name must contain at least one alphanumeric character."
        )

    # Additional security check: ensure no path traversal patterns remain
    if ".." in truncated or "/" in truncated or "\\" in truncated:
        raise ValidationError(
            f"Skill name '{name}' contains invalid path characters"
        )

    logger.info(f"[GitHub] Sanitized skill name: '{name}' -> '{truncated}'")
    return truncated


@dataclass
class GitHubPath:
    """Parsed GitHub URL components."""

    owner: str
    repo: str
    branch: str
    path: str  # e.g., "skills/brand-guidelines"


@dataclass
class GitHubFile:
    """File content downloaded from GitHub."""

    path: str  # Relative path within skill folder
    content: bytes


class GitHubSkillError(Exception):
    """Base exception for GitHub skill operations."""

    pass


class GitHubURLParseError(GitHubSkillError):
    """Raised when GitHub URL format is invalid."""

    pass


class GitHubDownloadError(GitHubSkillError):
    """Raised when downloading from GitHub fails."""

    pass


class GitHubDownloadService:
    """Download skill folders from GitHub.

    Uses the GitHub Contents API to recursively fetch all files from a
    specified directory in a repository.

    Example:
        service = GitHubDownloadService()
        github_path = service.parse_url(
            "https://github.com/anthropics/skills/tree/main/skills/brand-guidelines"
        )
        properties, files = await service.download_folder(github_path)
    """

    # Pattern to match GitHub tree URLs
    GITHUB_URL_PATTERN = re.compile(
        r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
        r"/tree/(?P<branch>[^/]+)/(?P<path>.+)"
    )

    def __init__(self, github_token: Optional[str] = None):
        """Initialize the download service.

        Args:
            github_token: Optional GitHub personal access token or app token.
                Provides higher rate limits (5000/hr vs 60/hr unauthenticated).
        """
        self._token = github_token
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> dict:
        """Get headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    def parse_url(self, github_url: str) -> GitHubPath:
        """Parse a GitHub URL into components.

        Args:
            github_url: GitHub URL in the format:
                https://github.com/{owner}/{repo}/tree/{branch}/{path}

        Returns:
            GitHubPath with parsed components

        Raises:
            GitHubURLParseError: If URL format is invalid
        """
        match = self.GITHUB_URL_PATTERN.match(github_url.strip())
        if not match:
            raise GitHubURLParseError(
                f"Invalid GitHub URL format. Expected: "
                f"https://github.com/owner/repo/tree/branch/path/to/skill. "
                f"Got: {github_url}"
            )

        return GitHubPath(
            owner=match.group("owner"),
            repo=match.group("repo"),
            branch=match.group("branch"),
            path=match.group("path").rstrip("/"),
        )

    async def download_folder(
        self, github_path: GitHubPath
    ) -> tuple[SkillProperties, list[GitHubFile]]:
        """Download a skill folder from GitHub.

        Uses the GitHub Contents API to recursively fetch all files.
        Validates that SKILL.md exists and parses its frontmatter.

        Args:
            github_path: Parsed GitHub path components

        Returns:
            Tuple of (SkillProperties, list of GitHubFile)

        Raises:
            GitHubDownloadError: If API request fails
            ParseError: If SKILL.md is missing or has invalid format
            ValidationError: If SKILL.md is missing required fields
        """
        client = await self._get_client()

        # Build API URL for directory contents
        api_url = (
            f"https://api.github.com/repos/{github_path.owner}/{github_path.repo}"
            f"/contents/{github_path.path}?ref={github_path.branch}"
        )

        try:
            response = await client.get(api_url)
            response.raise_for_status()
            contents = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise GitHubDownloadError(
                    f"Folder not found: {github_path.owner}/{github_path.repo}/{github_path.path}"
                )
            raise GitHubDownloadError(f"GitHub API error: {e}")
        except httpx.RequestError as e:
            raise GitHubDownloadError(f"Failed to connect to GitHub: {e}")

        if not isinstance(contents, list):
            raise GitHubDownloadError(
                f"Expected a directory at {github_path.path}, but found a file"
            )

        # Recursively download all files
        files: list[GitHubFile] = []
        await self._download_recursive(
            client=client,
            owner=github_path.owner,
            repo=github_path.repo,
            branch=github_path.branch,
            base_path=github_path.path,
            contents=contents,
            files=files,
        )

        # Find and parse SKILL.md
        skill_md_file = next(
            (f for f in files if f.path.lower() == "skill.md"),
            None,
        )

        if skill_md_file is None:
            raise ParseError(
                f"SKILL.md not found in {github_path.owner}/{github_path.repo}/{github_path.path}"
            )

        # Parse the SKILL.md content
        skill_md_content = skill_md_file.content.decode("utf-8")
        metadata, _ = parse_frontmatter(skill_md_content)

        # Validate required fields
        if "name" not in metadata:
            raise ValidationError("SKILL.md missing required field: name")
        if "description" not in metadata:
            raise ValidationError("SKILL.md missing required field: description")

        raw_name = metadata["name"]
        description = metadata["description"]

        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValidationError("Field 'name' must be a non-empty string")
        if not isinstance(description, str) or not description.strip():
            raise ValidationError("Field 'description' must be a non-empty string")

        # SECURITY: Sanitize skill name to prevent path traversal attacks
        # This converts the name to a safe slug (lowercase, alphanumeric, hyphens only)
        sanitized_name = sanitize_skill_name(raw_name.strip())
        logger.info(f"[GitHub] Using sanitized skill name: '{sanitized_name}' (original: '{raw_name.strip()}')")

        properties = SkillProperties(
            name=sanitized_name,
            description=description.strip(),
            license=metadata.get("license"),
            compatibility=metadata.get("compatibility"),
            allowed_tools=metadata.get("allowed-tools"),
            metadata=metadata.get("metadata") or {},
        )

        return properties, files

    async def _download_recursive(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        branch: str,
        base_path: str,
        contents: list,
        files: list[GitHubFile],
    ) -> None:
        """Recursively download directory contents.

        Args:
            client: HTTP client
            owner: Repository owner
            repo: Repository name
            branch: Branch name
            base_path: Base path for relative paths
            contents: List of content items from GitHub API
            files: Output list to append downloaded files
        """
        for item in contents:
            # Calculate relative path (remove base_path prefix)
            full_path = item["path"]
            if full_path.startswith(base_path + "/"):
                relative_path = full_path[len(base_path) + 1 :]
            else:
                relative_path = full_path

            if item["type"] == "file":
                # Download file content
                download_url = item.get("download_url")
                if not download_url:
                    logger.warning(f"No download URL for {full_path}, skipping")
                    continue

                try:
                    file_response = await client.get(download_url)
                    file_response.raise_for_status()
                    files.append(
                        GitHubFile(
                            path=relative_path,
                            content=file_response.content,
                        )
                    )
                    logger.debug(f"Downloaded: {relative_path}")
                except httpx.HTTPError as e:
                    logger.warning(f"Failed to download {relative_path}: {e}")
                    raise GitHubDownloadError(f"Failed to download {relative_path}: {e}")

            elif item["type"] == "dir":
                # Recursively get subdirectory contents
                subdir_url = (
                    f"https://api.github.com/repos/{owner}/{repo}"
                    f"/contents/{full_path}?ref={branch}"
                )

                try:
                    subdir_response = await client.get(subdir_url)
                    subdir_response.raise_for_status()
                    subdir_contents = subdir_response.json()

                    await self._download_recursive(
                        client=client,
                        owner=owner,
                        repo=repo,
                        branch=branch,
                        base_path=base_path,
                        contents=subdir_contents,
                        files=files,
                    )
                except httpx.HTTPError as e:
                    logger.warning(f"Failed to fetch subdirectory {full_path}: {e}")
                    raise GitHubDownloadError(
                        f"Failed to fetch subdirectory {full_path}: {e}"
                    )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "GitHubDownloadService":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
