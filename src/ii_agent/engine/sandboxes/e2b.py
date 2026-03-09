"""E2B Sandbox implementation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from functools import wraps
from typing import IO, TYPE_CHECKING, AsyncIterator, Dict, Any, List, Literal, Optional

from e2b import CommandResult, SandboxState
from e2b_code_interpreter import AsyncSandbox
from e2b_code_interpreter.models import Execution
from e2b.exceptions import (
    NotFoundException,
    AuthenticationException,
    TimeoutException,
)
from ii_agent.core.config.settings import get_settings
from ii_agent.engine.sandboxes.schemas import (
    SandboxInfo,
    SandboxProvider,
    SandboxStatus,
    SandboxFileInfo,
    FileUpload,
)
from ii_agent.engine.sandboxes.base import SandboxManager
from ii_agent.engine.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxNotFoundException,
    SandboxTimeoutException,
    SandboxNotInitializedError,
    SandboxOperationError,
)
from ii_agent.engine.sandboxes.models import Sandbox
from ii_agent.engine.sandboxes.sandbox_client import MCPClient
from fastmcp import Client

if TYPE_CHECKING:
    from ii_agent.integrations.connectors.composio.service import ComposioService
    from ii_agent.settings.mcp.service import MCPSettingService


logger = logging.getLogger(__name__)

# Default timeout constants
TIMEOUT_BUFFER_SECONDS = 3600  # 10 min buffer before hard timeout


def e2b_exception_handler(func):
    """Decorator to handle E2B-specific exceptions and convert to sandbox exceptions."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except NotFoundException as e:
            sandbox_id = "unknown"
            if args and hasattr(args[0], "sandbox_id"):
                sandbox_id = args[0].sandbox_id
            raise SandboxNotFoundException(str(sandbox_id)) from e
        except AuthenticationException as e:
            raise SandboxAuthenticationError(str(e)) from e
        except TimeoutException as e:
            sandbox_id = "unknown"
            if args and hasattr(args[0], "sandbox_id"):
                sandbox_id = args[0].sandbox_id
            raise SandboxTimeoutException(str(sandbox_id), func.__name__) from e
        except (
            SandboxNotFoundException,
            SandboxAuthenticationError,
            SandboxTimeoutException,
            SandboxNotInitializedError,
            SandboxOperationError,
        ):
            # Re-raise our own exceptions
            raise
        except Exception as e:
            raise SandboxOperationError(func.__name__, str(e)) from e

    return wrapper


class E2BSandboxManager(SandboxManager):
    """E2B sandbox manager for managing remote code execution environments with DB persistence.

    This implementation uses E2B's AsyncSandbox for cloud-based code execution
    and handles database persistence for sandbox state management.
    It supports creating, connecting to, pausing, and resuming sandboxes.

    Attributes:
        sandbox_id: Internal sandbox ID (our system's ID from database).
        session_id: Session ID this sandbox belongs to.
        provider_sandbox_id: E2B's sandbox ID.
        provider: Always "e2b" for this implementation.
        sandbox: E2B AsyncSandbox instance.
        metadata: Sandbox metadata.
        expired_at: Sandbox expiration time.
    """

    PROVIDER: SandboxProvider = "e2b"

    def __init__(
        self,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        status: SandboxStatus = SandboxStatus.NOT_INITIALIZED,
        metadata: Optional[Dict[str, Any]] = None,
        sandbox: Optional[AsyncSandbox] = None,
        expired_at: Optional[datetime] = None,
        mcp_setting_service: Optional[MCPSettingService] = None,
        composio_service: Optional[ComposioService] = None,
    ):
        """Initialize E2B sandbox manager.

        Args:
            sandbox_id: Internal sandbox ID (our system's ID from database).
            session_id: Session ID this sandbox belongs to.
            provider_sandbox_id: E2B's sandbox ID.
            status: Initial sandbox status.
            metadata: Sandbox metadata.
            sandbox: E2B AsyncSandbox instance.
            expired_at: Sandbox expiration time.
            mcp_setting_service: MCPSettingService instance (injected).
            composio_service: ComposioService instance (injected).
        """
        super().__init__(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=provider_sandbox_id,
            status=status,
        )
        self.metadata = metadata or {}
        self.sandbox = sandbox
        self.expired_at = expired_at
        self.mcp_client = None
        self._mcp_setting_service = mcp_setting_service
        self._composio_service = composio_service

    def get_provider_id(self) -> str:
        return self.provider_sandbox_id

    @property
    def upload_path(self) -> str:
        """Get the upload path for files in the sandbox."""
        return get_settings().workspace_upload_path

    async def get_info(self) -> SandboxInfo:
        vscode_url = None
        if self.status == SandboxStatus.RUNNING and self.sandbox:
            vscode_url = await self.expose_port(get_settings().vscode_port)
        return SandboxInfo(
            id=self.sandbox_id,
            session_id=self.session_id,
            status=self.status,
            expired_at=self.expired_at,
            provider=self.get_provider(),
            vscode_url=vscode_url,
        )

    @classmethod
    async def from_sandbox_record(cls, sandbox_record: Sandbox) -> Optional["E2BSandboxManager"]:
        """Create an E2BSandboxManager from an existing database record.

        This is a read-only operation that connects to the E2B sandbox
        without updating the database. Use this for status checks and
        read operations to avoid StaleDataError from optimistic locking
        conflicts on concurrent requests.
        """
        settings = get_settings()
        sandbox_info = await AsyncSandbox.get_info(
            sandbox_id=sandbox_record.provider_sandbox_id,
            api_key=settings.sandbox.e2b_api_key,
        )
        if not sandbox_info:
            return None
        status = cls._to_sandbox_state(sandbox_info.state)

        sandbox = None
        if status == SandboxStatus.RUNNING:
            try:
                sandbox = await AsyncSandbox.connect(
                    sandbox_id=sandbox_record.provider_sandbox_id,
                    api_key=settings.sandbox.e2b_api_key,
                    timeout=settings.sandbox.timeout_seconds,
                )
            except Exception as e:
                logger.warning(
                    "Failed to connect to E2B sandbox %s: %s",
                    sandbox_record.provider_sandbox_id,
                    e,
                )
                return None

        return cls(
            sandbox_id=str(sandbox_record.id),
            session_id=str(sandbox_record.session_id),
            provider_sandbox_id=sandbox_record.provider_sandbox_id,
            sandbox=sandbox,
            status=status,
            expired_at=sandbox_info.end_at,
        )

    @classmethod
    async def create(
        cls,
        sandbox_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        mcp_setting_service: Optional[MCPSettingService] = None,
        composio_service: Optional[ComposioService] = None,
    ) -> "E2BSandboxManager":
        """Create a new E2B sandbox with database persistence.

        Args:
            sandbox_id: Internal sandbox ID (from database).
            session_id: Session ID this sandbox belongs to.
            metadata: Optional metadata to attach.
            mcp_setting_service: MCPSettingService instance (injected).
            composio_service: ComposioService instance (injected).

        Returns:
            New E2BSandboxManager instance.
        """

        settings = get_settings()

        # Build metadata
        sandbox_metadata = {
            "ii_sandbox_id": sandbox_id,
            "session_id": session_id,
            "template_id": settings.sandbox.e2b_template_id,
        }

        if metadata:
            sandbox_metadata.update(metadata)

        expired_at = datetime.now(timezone.utc) + timedelta(
            seconds=settings.sandbox.timeout_seconds
        )

        # Create the E2B sandbox (OUTSIDE DB transaction)
        sandbox = await AsyncSandbox.beta_create(
            template=settings.sandbox.e2b_template_id,
            api_key=settings.sandbox.e2b_api_key,
            metadata=sandbox_metadata,
            auto_pause=True,
            timeout=settings.sandbox.timeout_seconds,
        )

        instance = cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=sandbox.sandbox_id,
            sandbox=sandbox,
            metadata=sandbox_metadata,
            status=SandboxStatus.RUNNING,
            expired_at=expired_at,
            mcp_setting_service=mcp_setting_service,
            composio_service=composio_service,
        )

        # Update database record (using common helper method)
        await instance._update_sandbox_db(
            status=SandboxStatus.RUNNING,
            provider_sandbox_id=sandbox.sandbox_id,
            expired_at=expired_at,
            provider_metadata=sandbox_metadata,
        )

        logger.info(
            f"Created E2B sandbox {sandbox_id} (provider: {sandbox.sandbox_id}) "
            f"with timeout {settings.sandbox.timeout_seconds}s"
        )

        return instance

    @staticmethod
    def _to_sandbox_state(sandbox_state: SandboxState) -> SandboxStatus:
        if sandbox_state.RUNNING:
            return SandboxStatus.RUNNING
        if sandbox_state.PAUSED:
            return SandboxStatus.PAUSED

        raise ValueError(f"Unrecognize sandbox status: {sandbox_state}")

    async def _ensure_sandbox_connection(self):
        if self.sandbox is None:
            raise SandboxNotInitializedError(
                f"Sandbox not yet initialized provider = {self.provider}, provider_id = {self.provider_sandbox_id}"
            )

        settings = get_settings()
        sandbox_info = await self.sandbox.get_info(
            sandbox_id=self.provider_sandbox_id,
            api_key=settings.sandbox.e2b_api_key,
        )
        timeout_buffer = timedelta(seconds=60)
        should_connect = (sandbox_info.state == SandboxState.PAUSED) or (
            sandbox_info.end_at < datetime.now(timezone.utc) - timeout_buffer
        )
        if should_connect:
            await self._connect(timeout_seconds=settings.sandbox.timeout_seconds)

    async def get_status(self) -> SandboxStatus:
        if self.sandbox is None:
            return SandboxStatus.INITIALIZING
        sandbox_info = await self.sandbox.get_info()
        return self._to_sandbox_state(sandbox_state=sandbox_info.state)

    @e2b_exception_handler
    async def _connect(self, timeout_seconds: int) -> "E2BSandboxManager":
        """Connect to an existing E2B sandbox (internal helper).

        Returns:
            Self (for chaining).
        """
        self.sandbox = await AsyncSandbox.connect(
            self.provider_sandbox_id,
            api_key=get_settings().sandbox.e2b_api_key,
            timeout=timeout_seconds,
        )
        self.status = SandboxStatus.RUNNING
        return self

    @classmethod
    async def connect(
        cls,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        mcp_setting_service: Optional[MCPSettingService] = None,
        composio_service: Optional[ComposioService] = None,
    ) -> "E2BSandboxManager":
        """Connect to an existing E2B sandbox with database persistence.

        Args:
            sandbox_id: Internal sandbox ID (from database).
            session_id: Session ID this sandbox belongs to.
            provider_sandbox_id: E2B sandbox ID to connect to.
            mcp_setting_service: MCPSettingService instance (injected).
            composio_service: ComposioService instance (injected).

        Returns:
            Connected E2BSandboxManager instance.
        """

        # Connect to E2B sandbox (OUTSIDE DB transaction)
        settings = get_settings()
        sandbox = await AsyncSandbox.connect(
            sandbox_id=provider_sandbox_id,
            api_key=settings.sandbox.e2b_api_key,
            timeout=settings.sandbox.timeout_seconds,
        )
        sandbox_info = await sandbox.get_info()
        status = cls._to_sandbox_state(sandbox_info.state)

        instance = cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=sandbox.sandbox_id,
            sandbox=sandbox,
            metadata=sandbox_info.metadata,
            status=status,
            expired_at=sandbox_info.end_at,
            mcp_setting_service=mcp_setting_service,
            composio_service=composio_service,
        )

        # Update database record (using common helper method)
        await instance._update_sandbox_db(
            status=status,
            expired_at=sandbox_info.end_at,
        )

        return instance

    @classmethod
    async def init(
        cls,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        mcp_setting_service: Optional[MCPSettingService] = None,
        composio_service: Optional[ComposioService] = None,
    ) -> "E2BSandboxManager":
        """Get existing sandbox for session or create new one (database-first approach).

        This method implements the container pattern from SandboxContainer:
        1. Try to get existing sandbox record from database
        2. If exists with provider_sandbox_id, connect to it
        3. If exists without provider_sandbox_id, create new E2B sandbox
        4. If doesn't exist, create DB record first then create E2B sandbox

        Args:
            session_id: Session ID this sandbox belongs to.
            metadata: Optional metadata to attach to new sandbox.
            mcp_setting_service: MCPSettingService instance (injected).
            composio_service: ComposioService instance (injected).

        Returns:
            E2BSandbox instance (either existing or newly created).
        """
        from ii_agent.core.db.manager import get_db_session_local
        from ii_agent.engine.sandboxes.repository import SandboxRepository

        service_kwargs = dict(
            mcp_setting_service=mcp_setting_service,
            composio_service=composio_service,
        )

        sandbox_repo = SandboxRepository()

        # Try to get or create database record
        async with get_db_session_local() as db_session:
            try:
                sandbox_record = await sandbox_repo.get_by_session_id(db_session, session_id)

                if not sandbox_record:
                    # Create new database record
                    sandbox_record = Sandbox(
                        session_id=session_id,
                        provider=cls.get_provider(),
                        status=SandboxStatus.INITIALIZING,
                    )
                    db_session.add(sandbox_record)
                    await db_session.flush()
                    await db_session.refresh(sandbox_record)
                    logger.info(
                        f"Created new sandbox record {sandbox_record.id} for session {session_id}"
                    )

            except Exception as e:
                logger.error(f"Failed to get or create sandbox record: {e}")
                raise

        # Now create or connect to E2B sandbox
        if sandbox_record.provider_sandbox_id:
            # Existing sandbox - try to connect to it
            logger.info(f"Connecting to existing E2B sandbox {sandbox_record.provider_sandbox_id}")
            try:
                return await cls.connect(
                    sandbox_id=str(sandbox_record.id),
                    session_id=sandbox_record.session_id,
                    provider_sandbox_id=sandbox_record.provider_sandbox_id,
                    **service_kwargs,
                )
            except (SandboxNotFoundException, SandboxOperationError) as e:
                # Sandbox expired or was deleted by E2B - create a new one
                # reusing the existing DB record
                logger.warning(
                    f"Existing E2B sandbox {sandbox_record.provider_sandbox_id} "
                    f"is no longer available ({e}), creating a new one"
                )
                return await cls.create(
                    sandbox_id=str(sandbox_record.id),
                    session_id=sandbox_record.session_id,
                    metadata=metadata,
                    **service_kwargs,
                )
        else:
            # New sandbox - create it
            logger.info(f"Creating new E2B sandbox for session {session_id}")
            return await cls.create(
                sandbox_id=str(sandbox_record.id),
                session_id=sandbox_record.session_id,
                metadata=metadata,
                **service_kwargs,
            )

    @e2b_exception_handler
    async def pause(self) -> None:
        """Pause the sandbox for later resumption."""
        is_running = await self.sandbox.is_running()
        if is_running:
            # Pause E2B sandbox (OUTSIDE DB transaction)
            await self.sandbox.beta_pause()
            self.status = SandboxStatus.PAUSED

            # Update database record (using common helper method)
            await self._update_sandbox_db(status=SandboxStatus.PAUSED)

            logger.info(f"Paused sandbox {self.sandbox_id} (provider: {self.provider_sandbox_id})")

    @e2b_exception_handler
    async def set_timeout(self, timeout_seconds: int) -> None:
        """Set or update the sandbox timeout.

        Args:
            timeout_seconds: Seconds until the sandbox times out.
        """
        # Add buffer to give time for pause before hard timeout
        await self.sandbox.set_timeout(timeout=timeout_seconds)
        self.expired_at = self.expired_at + timedelta(seconds=timeout_seconds)
        logger.debug(
            f"Set timeout for sandbox (provider: {self.provider_sandbox_id}): {timeout_seconds}s"
        )

    @e2b_exception_handler
    async def run_command(
        self,
        command: str,
        background: bool = False,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        **kwargs,
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
        await self._ensure_sandbox_connection()
        result = await self.sandbox.commands.run(
            command,
            background=background,
            timeout=timeout,
            cwd=cwd,
            **kwargs,
        )

        if not isinstance(result, CommandResult):
            raise SandboxOperationError("run_command", f"Unexpected result: {result}")

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or f"Exit code: {result.exit_code}"
            raise SandboxOperationError("run_command", f"Command failed: {error_msg}")

        return result.stdout

    @e2b_exception_handler
    async def run_python_code(self, code: str, timeout: int = 120) -> str:
        """Run Python code in the sandbox."""
        await self._ensure_sandbox_connection()
        result = await self.sandbox.run_code(
            code,
            language="python",
            background=False,
            timeout=timeout,
            cwd=None,
        )

        if not isinstance(result, Execution):
            raise SandboxOperationError("run_python_code", f"Unexpected result: {result}")

        if result.error:
            raise SandboxOperationError("run_python_code", f"Execution failed:{result.error.name} {result.error.value}")

        return result.results[0].text or ""

    @e2b_exception_handler
    async def read_file(self, file_path: str) -> str:
        """Read a file from the sandbox."""
        await self._ensure_sandbox_connection()
        content = await self.sandbox.files.read(file_path, format="text")
        return content

    @e2b_exception_handler
    async def write_file(
        self,
        file_path: str,
        content: str | bytes | IO,
    ) -> SandboxFileInfo:
        """Write content to a file in the sandbox."""
        await self._ensure_sandbox_connection()
        write_info = await self.sandbox.files.write(file_path, content)
        return SandboxFileInfo(
            name=write_info.name,
            type="file",
            path=file_path,
        )

    @e2b_exception_handler
    async def write_files(self, files: List[FileUpload]) -> List[SandboxFileInfo]:
        """Write content to a file in the sandbox."""
        await self._ensure_sandbox_connection()
        files = [{"path": file.path, "content": file.content} for file in files]
        results = await self.sandbox.files.write_files(files)
        return [
            SandboxFileInfo(
                name=r.name,
                type=r.type.value,
                path=r.path,
            )
            for r in results
        ]

    @e2b_exception_handler
    async def upload_file(
        self,
        file_content: str | bytes | IO,
        remote_file_path: str,
    ) -> bool:
        """Upload a file to the sandbox."""
        await self._ensure_sandbox_connection()
        if await self.sandbox.files.exists(remote_file_path):
            logger.warning(f"File {remote_file_path} already exists, overwriting")

        await self.sandbox.files.write(remote_file_path, file_content)

        return True

    @e2b_exception_handler
    async def download_file(
        self,
        remote_file_path: str,
        format: Literal["text", "bytes"] = "text",
    ) -> Optional[str | bytes]:
        """Download a file from the sandbox."""
        await self._ensure_sandbox_connection()
        content = await self.sandbox.files.read(path=remote_file_path, format=format)
        if isinstance(content, bytes):
            return content
        elif isinstance(content, bytearray):
            return bytes(content)
        elif isinstance(content, str):
            return content if format == "text" else content.encode("utf-8")
        else:
            raise SandboxOperationError(
                "download_file", f"Unsupported content type: {type(content)}"
            )

    async def download_file_stream(
        self,
        remote_file_path: str,
    ) -> AsyncIterator[bytes]:
        """Download a file from the sandbox as a stream."""
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.read(path=remote_file_path, format="stream")

    @e2b_exception_handler
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from the sandbox."""
        await self._ensure_sandbox_connection()
        await self.sandbox.files.remove(file_path)
        return True

    @e2b_exception_handler
    async def create_directory(
        self,
        directory_path: str,
        exist_ok: bool = False,
    ) -> bool:
        """Create a directory in the sandbox."""
        await self._ensure_sandbox_connection()
        created = await self.sandbox.files.make_dir(directory_path)
        if not created and not exist_ok:
            raise SandboxOperationError(
                "create_directory", f"Directory {directory_path} already exists"
            )
        return True

    @e2b_exception_handler
    async def file_exists(self, file_path: str) -> bool:
        """Check if a file exists in the sandbox."""
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.exists(file_path)

    async def expose_port(self, port: int) -> str:
        await self._ensure_sandbox_connection()
        host = self.sandbox.get_host(port)
        return f"https://{host}"

    async def get_host(self) -> str:
        """Get the sandbox host address."""
        return f"{self.provider_sandbox_id}.{self.sandbox.connection_config.domain}"

    async def configure_sandbox_mcp(self, user_id) -> None:
        if self.sandbox is None:
            logger.warning(f"Sandbox is not yet initialized for session: {self.session_id}")
            return
        sandbox_url = await self.expose_port(get_settings().mcp.port)
        credentials = {
            "session_id": str(self.session_id),
            "host_url": "-".join(sandbox_url.split("-")[1:])
        }
        self.get_mcp_client(sandbox_url=sandbox_url)
        await self._pre_configure_mcp_server(credentials, sandbox_url)
        await self._register_user_mcp_servers(user_id, sandbox_url)

    def get_mcp_client(self, sandbox_url) -> Client:
        mcp_url = sandbox_url + "/mcp/"
        if self.mcp_client is None:
            self.mcp_client = Client(mcp_url, timeout=get_settings().mcp.timeout)
        return self.mcp_client

    async def _pre_configure_mcp_server(self, credential: Dict, sandbox_url):
        """Set the tool server url for the sandbox."""
        async with MCPClient(sandbox_url) as client:
            try:
                await client.set_credential(credential)
                await client.set_tool_server_url(get_settings().tool_server_url)
            except Exception as e:
                logger.warning(f"Error when setting tool server: {str(e)}")
            # Ensure that service is available

            await client.ping()
            await client.list_tools()
        return True

    async def _register_user_mcp_servers(self, user_id: str, sandbox_url) -> bool:
        """Register user's MCP servers with the sandbox.

        Returns:
            bool: True if registration succeeded or no servers to register, False on error
        """
        if self._mcp_setting_service is None:
            raise SandboxOperationError(
                "_register_user_mcp_servers",
                "mcp_setting_service is required but was not injected",
            )
        from ii_agent.core.db.manager import get_db_session_local
        from ii_agent.settings.mcp.schemas import ClaudeCodeMetadata, CodexMetadata
        # Query active MCP settings for user
        async with get_db_session_local() as db_session:
            mcp_settings = await self._mcp_setting_service.list_mcp_settings(
                db_session, user_id=user_id, only_active=True
            )

        # Get combined configuration using the new method
        combined_config = mcp_settings.get_combined_active_config() if mcp_settings.settings else None

        # Convert to dict for registration
        config_dict = combined_config.model_dump(exclude_none=True) if combined_config else {}

        # Get Composio MCP servers
        composio_mcp_servers = await self._get_composio_mcp_servers(user_id)

        # Merge both MCP server configurations
        merged_mcp_servers = {}
        if config_dict.get("mcpServers"):
            merged_mcp_servers.update(config_dict["mcpServers"])
        if composio_mcp_servers:
            merged_mcp_servers.update(composio_mcp_servers)

        # Register with sandbox using MCPClient
        settings = get_settings()
        async with MCPClient(sandbox_url) as client:
            # Handle Codex and Claude Code metadata
            if combined_config:
                is_codex = any(
                    isinstance(metadata, CodexMetadata) for metadata in combined_config.metadatas
                )

                for metadata in combined_config.metadatas:
                    if isinstance(metadata, CodexMetadata):
                        store_path = f"{settings.sandbox.user}/.codex/auth.json"
                        await self.write_file(store_path, json.dumps(metadata.auth_json))
                    if isinstance(metadata, ClaudeCodeMetadata):
                        store_path = f"{settings.sandbox.user}/.claude/.credentials.json"
                        await self.write_file(store_path, json.dumps(metadata.auth_json))

                if is_codex:
                    logger.info("Codex metadata found, ensuring Codex setup in sandbox")
                    await client.register_codex()
                else:
                    logger.info("No Codex metadata found, skipping Codex setup")

            # Register all MCP servers in a single call
            if merged_mcp_servers:
                logger.info(
                    f"Registering {len(merged_mcp_servers)} MCP servers for user {user_id} "
                    f"(custom: {len(config_dict.get('mcpServers', {}))}, "
                    f"composio: {len(composio_mcp_servers or {})})"
                )
                merged_config_dict = {"mcpServers": merged_mcp_servers}
                await client.register_custom_mcp(merged_config_dict)
            else:
                logger.info(f"No MCP servers to register for user {user_id}")

        return True

    async def _get_composio_mcp_servers(self, user_id: str) -> Optional[Dict]:
        """Get user's Composio MCP server configurations.

        Returns:
            Optional[Dict]: Dictionary of Composio MCP servers, or None if none found or on error
        """
        if self._composio_service is None:
            logger.debug("composio_service not injected, skipping Composio MCP servers")
            return None

        try:
            from ii_agent.core.db.manager import get_db_session_local

            async with get_db_session_local() as db_session:
                composio_mcp_servers = await self._composio_service.get_user_composio_mcp_configs(db_session, user_id)

            if not composio_mcp_servers:
                logger.debug(f"No Composio profiles found for user {user_id}")
                return None

            logger.info(f"Found {len(composio_mcp_servers)} Composio MCP servers for user {user_id}")
            return composio_mcp_servers

        except Exception as e:
            logger.error(
                f"Failed to get Composio MCP servers for user {user_id}: {e}",
                exc_info=True
            )
            # Don't fail the entire sandbox setup if Composio fetch fails
            return None
