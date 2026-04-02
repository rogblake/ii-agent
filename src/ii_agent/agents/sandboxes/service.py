"""Sandbox service — orchestrates DB persistence + provider lifecycle + MCP config.

This is the single entry point for sandbox operations.  The agent and
socket handlers should call :class:`SandboxService` instead of touching
the provider (E2B, Docker, ...) or the database directly.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.e2b import E2BSandbox
from ii_agent.agents.sandboxes.exceptions import SandboxCreationError
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings
from ii_agent.core.logger import logger
from ii_agent.sessions.repository import SessionRepository


class SandboxService:
    """Manages sandbox lifecycle with database persistence.

    Responsibilities:
    - Find-or-create sandbox records in the database
    - Delegate to the correct provider (E2B / Docker) for provisioning
    - Persist provider state back to the database
    - Configure MCP servers on newly created sandboxes
    """

    def __init__(
        self,
        sandbox_repo: SandboxRepository,
        session_repo: SessionRepository,
        config: Settings,
    ) -> None:
        self._sandbox_repo = sandbox_repo
        self._session_repo = session_repo
        self._config = config

    # ── Public API ────────────────────────────────────────────────────────

    async def init_sandbox(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Sandbox:
        """Get or create a sandbox for the given session.

        1. Look for an existing active sandbox record.
        2. If the session is a fork, look up parent's sandbox via ``parent_session_id``.
        3. Otherwise, create a new DB record and provision via the provider.
        4. Configure MCP servers on newly created sandboxes.

        Returns the ready-to-use :class:`Sandbox`.
        """
        # 1. Try existing record, then fall back to the parent's sandbox for forks.
        record = await self._resolve_sandbox_record(db, session_id)

        # 3. Create new record if none found
        is_new = False
        if record is None:
            provider = self._resolve_provider()
            record = AgentSandbox(
                session_id=session_id,
                provider=provider,
                status=SandboxStatus.INITIALIZING,
            )
            record = await self._sandbox_repo.save(db, record)
            is_new = True
            logger.info(f"Created sandbox record {record.id} for session {session_id}")

        # 4. Connect or create provider sandbox
        if record.provider_sandbox_id:
            sandbox_mgr = await self._connect_provider(record)
        else:
            sandbox_mgr = await self._create_provider(record, metadata)

        # 5. Persist provider state
        await self._sandbox_repo.update_provider_info(
            db,
            record.id,
            status=sandbox_mgr.status,
            provider_sandbox_id=sandbox_mgr.provider_sandbox_id,
            expired_at=sandbox_mgr.expired_at,
            provider_data=sandbox_mgr.metadata,
        )

        # 6. Configure MCP on new sandboxes
        if is_new or not record.provider_sandbox_id:
            await self._configure_mcp(sandbox_mgr, user_id, db)

        return sandbox_mgr

    async def get_sandbox_for_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[Sandbox]:
        """Get existing sandbox for a session without creating one."""
        record = await self._resolve_sandbox_record(
            db,
            session_id,
            require_provider_sandbox_id=True,
        )
        if record is None:
            return None
        try:
            return await self._connect_provider(record)
        except Exception:
            logger.warning(f"Failed to connect to sandbox {record.id}", exc_info=True)
            return None

    async def get_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[AgentSandbox]:
        """Get the active sandbox record for a session, falling back to the parent."""
        return await self._resolve_sandbox_record(db, session_id)

    async def pause_sandbox(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
    ) -> None:
        """Pause a sandbox and update the database."""
        record = await self._sandbox_repo.get_by_id(db, sandbox_id)
        if record is None or record.provider_sandbox_id is None:
            return
        try:
            sandbox_mgr = await self._connect_provider(record)
            await sandbox_mgr.pause()
            await self._sandbox_repo.update_status(db, sandbox_id, SandboxStatus.PAUSED)
        except Exception:
            logger.error(f"Failed to pause sandbox {sandbox_id}", exc_info=True)

    async def update_status(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        status: SandboxStatus,
    ) -> None:
        """Update sandbox status in database."""
        await self._sandbox_repo.update_status(db, sandbox_id, status)

    # ── Provider resolution ───────────────────────────────────────────────

    def _resolve_provider(self) -> SandboxProviderType:
        """Map config ``sandbox.provider`` to our enum."""
        provider = self._config.sandbox.provider
        if provider == "e2b":
            return SandboxProviderType.E2B
        if provider == "docker":
            return SandboxProviderType.DOCKER
        raise SandboxCreationError(f"Unsupported sandbox provider: {provider}")

    async def _create_provider(
        self,
        record: AgentSandbox,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Sandbox:
        """Provision a new sandbox via the correct provider."""
        if record.provider == SandboxProviderType.E2B:
            return await E2BSandbox.create(
                sandbox_id=str(record.id),
                session_id=str(record.session_id),
                metadata=metadata,
            )
        raise SandboxCreationError(f"Unsupported provider: {record.provider}")

    async def _connect_provider(self, record: AgentSandbox) -> Sandbox:
        """Connect to an existing provider sandbox."""
        if record.provider == SandboxProviderType.E2B:
            return await E2BSandbox.connect(
                sandbox_id=str(record.id),
                session_id=str(record.session_id),
                provider_sandbox_id=record.provider_sandbox_id,
            )
        raise SandboxCreationError(f"Unsupported provider: {record.provider}")

    async def _resolve_sandbox_record(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        *,
        require_provider_sandbox_id: bool = False,
    ) -> Optional[AgentSandbox]:
        """Resolve the active sandbox record for a session or its parent."""

        def _usable(record: AgentSandbox | None) -> bool:
            return record is not None and (
                not require_provider_sandbox_id or record.provider_sandbox_id is not None
            )

        record = await self._sandbox_repo.get_active_by_session_id(db, session_id)
        if _usable(record):
            return record

        session = await self._session_repo.get_by_id(db, session_id)
        if session and session.parent_session_id:
            parent_record = await self._sandbox_repo.get_active_by_session_id(
                db, session.parent_session_id
            )
            if _usable(parent_record):
                logger.info(
                    "Session %s sharing sandbox from parent %s",
                    session_id,
                    session.parent_session_id,
                )
                return parent_record

        if require_provider_sandbox_id:
            return None
        return record

    # ── MCP configuration ─────────────────────────────────────────────────

    async def _configure_mcp(
        self,
        sandbox: Sandbox,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Configure MCP servers on a sandbox."""
        try:
            sandbox_url = await sandbox.expose_port(self._config.mcp.port)
            # Build and set credentials
            sandbox.get_mcp_client(sandbox_url=sandbox_url)

            # Register user MCP servers
            await self._register_user_mcp_servers(sandbox, user_id, sandbox_url, db)

        except Exception as e:
            logger.warning(f"Failed to configure MCP for sandbox {sandbox.sandbox_id}: {e}")

    async def _register_user_mcp_servers(
        self,
        sandbox: Sandbox,
        user_id: uuid.UUID,
        sandbox_url: str,
        db: AsyncSession,
    ) -> None:
        """Register user's custom + composio MCP servers with the sandbox."""
        from ii_agent.settings.mcp.service import MCPSettingService
        from ii_agent.settings.mcp.repository import MCPSettingRepository
        from ii_agent.settings.mcp.schemas import CodexMetadata, ClaudeCodeMetadata
        from ii_server.mcp.client import MCPClient

        mcp_svc = MCPSettingService(repo=MCPSettingRepository(), config=self._config)
        mcp_settings = await mcp_svc.list_mcp_settings(db, user_id=str(user_id), only_active=True)

        combined_config = (
            mcp_settings.get_combined_active_config() if mcp_settings.settings else None
        )
        config_dict = combined_config.model_dump(exclude_none=True) if combined_config else {}

        # Get composio servers
        composio_mcp_servers = await self._get_composio_mcp_servers(user_id, db)

        merged_mcp_servers: dict = {}
        if config_dict.get("mcpServers"):
            merged_mcp_servers.update(config_dict["mcpServers"])
        if composio_mcp_servers:
            merged_mcp_servers.update(composio_mcp_servers)

        async with MCPClient(sandbox_url) as client:
            if combined_config:
                is_codex = any(isinstance(m, CodexMetadata) for m in combined_config.metadatas)
                for md in combined_config.metadatas:
                    if isinstance(md, CodexMetadata):
                        store_path = f"{self._config.sandbox.user}/.codex/auth.json"
                        await sandbox.write_file(store_path, json.dumps(md.auth_json))
                    if isinstance(md, ClaudeCodeMetadata):
                        store_path = f"{self._config.sandbox.user}/.claude/.credentials.json"
                        await sandbox.write_file(store_path, json.dumps(md.auth_json))

                if is_codex:
                    logger.info("Codex metadata found, ensuring Codex setup in sandbox")
                    await client.register_codex()

            if merged_mcp_servers:
                logger.info(f"Registering {len(merged_mcp_servers)} MCP servers for user {user_id}")
                await client.register_custom_mcp({"mcpServers": merged_mcp_servers})

    async def _get_composio_mcp_servers(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> Optional[dict]:
        """Get user's Composio MCP server configurations."""
        try:
            # Use the composio service to get decrypted MCP configs
            from ii_agent.core.container import get_app_container

            container = get_app_container()
            composio_mcp_servers = await container.composio_service.get_user_composio_mcp_configs(
                db, user_id
            )
            if not composio_mcp_servers:
                return None

            logger.info(
                f"Found {len(composio_mcp_servers)} Composio MCP servers for user {user_id}"
            )
            return composio_mcp_servers
        except Exception as e:
            logger.error(f"Failed to get Composio MCP servers for user {user_id}: {e}")
            return None
