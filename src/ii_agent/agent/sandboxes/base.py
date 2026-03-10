"""Base sandbox manager abstract class.

This module defines the abstract interface for sandbox manager providers,
enabling multi-provider support with a consistent API and database persistence.
"""

from abc import ABC, abstractmethod
import logging
from typing import IO, AsyncIterator, Dict, Any, List, Literal, Optional

from fastmcp import Client

from ii_agent.agent.sandboxes.schemas import (
    SandboxFileInfo,
    SandboxInfo,
    SandboxProvider,
    SandboxStatus,
    FileUpload,
)

logger = logging.getLogger(__name__)


class SandboxManager(ABC):
    """Abstract base class for sandbox manager providers.

    A sandbox provides an isolated execution environment for running
    code, commands, and file operations safely with database persistence.

    Implementations must provide:
    - Lifecycle methods: create, connect, pause
    - Command execution: run_command
    - File operations: read_file, write_file, upload_file, download_file, etc.

    Attributes:
        sandbox_id: Internal sandbox ID (our system's ID from database).
        session_id: Session ID this sandbox belongs to.
        provider_sandbox_id: Provider-specific sandbox ID (e.g., E2B's ID).
        provider: Provider name (e.g., "e2b", "docker").
        status: Current sandbox status.
    """

    PROVIDER: SandboxProvider

    def __init__(
        self,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        status: SandboxStatus = SandboxStatus.NOT_INITIALIZED,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize sandbox manager.

        Args:
            sandbox_id: Internal sandbox ID (our system's ID from database).
            session_id: Session ID this sandbox belongs to.
            provider_sandbox_id: Provider-specific sandbox ID.
            status: Initial sandbox status.
        """
        self.sandbox_id = sandbox_id
        self.session_id = session_id
        self.provider_sandbox_id = provider_sandbox_id
        self.status = status
        self.provider = self.get_provider()
        self.metadata = metadata

    @classmethod
    def get_provider(cls) -> SandboxProvider:
        """Get the provider name for this sandbox implementation."""
        if not getattr(cls, "PROVIDER", None):
            raise NotImplementedError("Sandbox provider not configured")
        return cls.PROVIDER

    @abstractmethod
    async def get_info(self) -> SandboxInfo:
        pass

    @property
    @abstractmethod
    def upload_path(self) -> str:
        """Get the upload path for files in the sandbox."""
        pass

    @abstractmethod
    def get_provider_id(self) -> str:
        """Get the provider-specific sandbox ID."""
        pass

    @abstractmethod
    def get_mcp_client(self, sandbox_url) -> Client:
        pass

    async def _update_sandbox_db(
        self,
        status: Optional[SandboxStatus] = None,
        provider_sandbox_id: Optional[str] = None,
        expired_at: Optional[Any] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update sandbox record in database with optimistic locking.

        Args:
            status: New status to set (optional).
            provider_sandbox_id: Provider sandbox ID to set (optional).
            expired_at: Expiration time to set (optional).
            provider_metadata: Provider metadata to set (optional).
        """
        from sqlalchemy.orm.exc import StaleDataError
        from ii_agent.agent.sandboxes.service import SandboxService
        from ii_agent.agent.sandboxes.repository import SandboxRepository
        from ii_agent.core.config.settings import get_settings
        from ii_agent.core.db.manager import get_db_session_local

        try:
            async with get_db_session_local() as db_session:
                sandbox_record = await SandboxService(config=get_settings(), sandbox_repo=SandboxRepository()).get_by_id(db_session, self.sandbox_id)
                if sandbox_record:
                    if status is not None:
                        sandbox_record.status = status
                    if provider_sandbox_id is not None:
                        sandbox_record.provider_sandbox_id = provider_sandbox_id
                    if expired_at is not None:
                        sandbox_record.expired_at = expired_at
                    if provider_metadata is not None:
                        sandbox_record.provider_data = provider_metadata

                    await db_session.flush()
        except StaleDataError:
            logger.warning(
                "Optimistic locking conflict updating sandbox %s "
                "(concurrent update detected, skipping)",
                self.sandbox_id,
            )

    async def store_and_cleanup(self) -> None:
        """Pause the sandbox and update database state (common implementation).

        This method should be called when you want to preserve the sandbox
        for later use. It pauses the sandbox and updates the database status.
        """
        # Pause the sandbox (provider-specific)
        await self.pause()
        # Status is already updated in pause() via _update_sandbox_db()

    @abstractmethod
    async def get_status(self) -> SandboxStatus:
        """Get the current sandbox status."""
        pass

    @classmethod
    @abstractmethod
    async def create(
        cls,
        sandbox_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "SandboxManager":
        """Create a new sandbox instance.

        Args:
            sandbox_id: Internal sandbox ID.
            session_id: Session ID this sandbox belongs to.
            metadata: Optional metadata to attach to the sandbox.

        Returns:
            New sandbox instance.
        """
        pass

    @classmethod
    @abstractmethod
    async def connect(cls, provider_sandbox_id: str) -> "SandboxManager":
        """Connect to an existing sandbox instance.

        Returns:
            Connected sandbox instance (self).
        """
        pass

    @abstractmethod
    async def pause(self) -> None:
        """Pause the sandbox for later resumption."""
        pass

    @abstractmethod
    async def set_timeout(self, timeout_seconds: int) -> None:
        """Set or update the sandbox timeout.

        Args:
            timeout_seconds: Seconds until the sandbox times out.
        """
        pass

    @abstractmethod
    async def run_command(
        self,
        command: str,
        background: bool = False,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
    ) -> str:
        """Run a command in the sandbox.

        Args:
            command: Command to run.
            background: If True, run in background.
            timeout: Optional command timeout in seconds.
            cwd: Optional working directory.

        Returns:
            Command output (stdout).
        """
        pass

    @abstractmethod
    async def run_python_code(self, code: str) -> str:
        """Run Python code in the sandbox.

        Args:
            code: Code to run.

        Returns:
            Code output (stdout).
        """
        pass

    @abstractmethod
    async def read_file(self, file_path: str) -> str:
        """Read a file from the sandbox.

        Args:
            file_path: Path to the file in the sandbox.

        Returns:
            File content as string.
        """
        pass

    @abstractmethod
    async def write_file(
        self,
        file_path: str,
        content: str | bytes | IO,
    ) -> SandboxFileInfo:
        """Write content to a file in the sandbox.

        Args:
            file_path: Path to the file in the sandbox.
            content: Content to write.

        Returns:
            True if written successfully.
        """
        pass

    @abstractmethod
    async def write_files(self, files: List[FileUpload]) -> List[SandboxFileInfo]:
        """Write content to a file in the sandbox.

        Args:
            file_path: Path to the file in the sandbox.
            content: Content to write.

        Returns:
            True if written successfully.
        """
        pass

    @abstractmethod
    async def upload_file(
        self,
        file_content: str | bytes | IO,
        remote_file_path: str,
    ) -> bool:
        """Upload a file to the sandbox.

        Args:
            file_content: Content of the file.
            remote_file_path: Path to the file in the sandbox.

        Returns:
            True if uploaded successfully.
        """
        pass

    @abstractmethod
    async def download_file(
        self,
        remote_file_path: str,
        format: Literal["text", "bytes"] = "text",
    ) -> Optional[str | bytes]:
        """Download a file from the sandbox.

        Args:
            remote_file_path: Path to the file in the sandbox.
            format: Format of the file content.

        Returns:
            File content as string or bytes.
        """
        pass

    @abstractmethod
    async def download_file_stream(
        self,
        remote_file_path: str,
    ) -> AsyncIterator[bytes]:
        """Download a file from the sandbox as a stream.

        Args:
            remote_file_path: Path to the file in the sandbox.

        Returns:
            Async iterator of bytes.
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from the sandbox.

        Args:
            file_path: Path to the file in the sandbox.

        Returns:
            True if deleted successfully.
        """
        pass

    @abstractmethod
    async def create_directory(
        self,
        directory_path: str,
        exist_ok: bool = False,
    ) -> bool:
        """Create a directory in the sandbox.

        Args:
            directory_path: Path to the directory.
            exist_ok: If True, do not raise error if directory exists.

        Returns:
            True if created successfully.
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists in the sandbox.

        Args:
            file_path: Path to the file.

        Returns:
            True if file exists.
        """
        pass

    @abstractmethod
    async def expose_port(self, port: int) -> str:
        """Expose a port in the sandbox.

        Args:
            port: Port to expose.

        Returns:
            URL to access the port.
        """
        pass

    async def upload_file_from_url(self, url: str, remote_file_path: str) -> bool:
        """Upload a file from a URL to the sandbox.

        Default implementation downloads the URL content then uploads via upload_file.

        Args:
            url: URL to download from.
            remote_file_path: Path to store the file in the sandbox.

        Returns:
            True if uploaded successfully.
        """
        import httpx

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        return await self.upload_file(response.content, remote_file_path)

    @abstractmethod
    async def get_host(self) -> str:
        """Get the sandbox host address.

        Returns:
            Host address string.
        """
        pass
