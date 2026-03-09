"""Sandbox service wrapping SandboxManager for sandbox lifecycle management."""

from __future__ import annotations

import uuid
import logging
import asyncio
from typing import TYPE_CHECKING, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.engine.sandboxes.base import SandboxManager
from ii_agent.engine.sandboxes.e2b import E2BSandboxManager
from ii_agent.engine.sandboxes.models import Sandbox
from ii_agent.engine.sandboxes.schemas import SandboxStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.engine.sandboxes.exceptions import SandboxNotFoundException
from ii_agent.engine.sandboxes.repository import SandboxRepository

if TYPE_CHECKING:
    from ii_agent.integrations.connectors.composio.service import ComposioService
    from ii_agent.settings.mcp.service import MCPSettingService

logger = logging.getLogger(__name__)

MAX_ATTEMPT = 3
RETRY_DELAY_SECONDS = 1


class SandboxService:
    """Sandbox service that manages SandboxManager lifecycle per session.

    Follows the same pattern as ProjectService: accepts ``db: AsyncSession``
    from callers so that DB reads and SandboxManager interactions share the
    same transactional scope.  If a provider operation fails the caller's
    transaction is rolled back automatically.
    """

    def __init__(
        self,
        *,
        sandbox_repo: SandboxRepository,
        config: Settings,
        mcp_setting_service: Optional[MCPSettingService] = None,
        composio_service: Optional[ComposioService] = None,
    ):
        self._config = config
        self._repo = sandbox_repo
        self._mcp_setting_service = mcp_setting_service
        self._composio_service = composio_service

    # ── SandboxManager methods (DB + provider in one scope) ────────────

    async def get_sandbox_by_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: str | None = None,
    ) -> SandboxManager:
        """Get or create a sandbox for the given session.

        Creates E2BSandboxManager via init() which handles the DB-first approach,
        then configures MCP servers if *user_id* is provided.
        """
        session_id_str = str(session_id)
        service_kwargs = dict(
            mcp_setting_service=self._mcp_setting_service,
            composio_service=self._composio_service,
        )

        last_error = None
        for attempt in range(MAX_ATTEMPT):
            try:
                sandbox = await E2BSandboxManager.init(
                    session_id=session_id_str,
                    **service_kwargs,
                )

                if user_id:
                    await sandbox.configure_sandbox_mcp(user_id)

                return sandbox
            except Exception as e:
                last_error = e
                logger.warning(
                    "Sandbox initialization failed for session %s (attempt %d/%d): %s",
                    session_id,
                    attempt + 1,
                    MAX_ATTEMPT,
                    str(e),
                    exc_info=True,
                )
                if attempt < MAX_ATTEMPT - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        raise RuntimeError(
            f"Failed to initialize sandbox for session {session_id} after {MAX_ATTEMPT} attempts"
        ) from last_error

    async def get_sandbox_by_session_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> SandboxManager | None:
        """Get existing sandbox for a session (without creating)."""
        sandbox_record = await self._repo.get_by_session_id(
            db, str(session_id)
        )

        if not sandbox_record or not sandbox_record.provider_sandbox_id:
            return None

        return await E2BSandboxManager.from_sandbox_record(sandbox_record)

    async def get_sandbox_status_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> str:
        """Get sandbox status by session ID."""
        sandbox_record = await self._repo.get_by_session_id(
            db, str(session_id)
        )

        if not sandbox_record or not sandbox_record.provider_sandbox_id:
            return SandboxStatus.NOT_INITIALIZED.value

        try:
            sandbox = await E2BSandboxManager.from_sandbox_record(
                sandbox_record
            )
            if sandbox:
                status = await sandbox.get_status()
                return status.value
        except Exception as e:
            logger.warning(
                f"Failed to get sandbox status for session {session_id}: {e}"
            )

        return SandboxStatus.NOT_INITIALIZED.value

    async def wake_up_sandbox_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> SandboxManager | None:
        """Wake up a paused sandbox by session ID."""
        sandbox_record = await self._repo.get_by_session_id(
            db, str(session_id)
        )

        if not sandbox_record or not sandbox_record.provider_sandbox_id:
            raise SandboxNotFoundException(str(session_id))

        return await E2BSandboxManager.connect(
            sandbox_id=str(sandbox_record.id),
            session_id=str(sandbox_record.session_id),
            provider_sandbox_id=sandbox_record.provider_sandbox_id,
        )

    async def cleanup_sandbox_for_session(
        self,
        db: AsyncSession,
        session_uuid: uuid.UUID,
        time_til_clean_up: Optional[int] = None,
    ):
        """Schedule a timeout for a session's sandbox."""
        if time_til_clean_up is None:
            time_til_clean_up = self._config.sandbox.time_til_clean_up

        sandbox_record = await self._repo.get_by_session_id(
            db, str(session_uuid)
        )

        if not sandbox_record or not sandbox_record.provider_sandbox_id:
            logger.info(f"Session {session_uuid} has no sandbox to clean up")
            return

        try:
            sandbox = await E2BSandboxManager.from_sandbox_record(
                sandbox_record
            )
            if sandbox:
                await sandbox.set_timeout(time_til_clean_up)
        except Exception as e:
            logger.warning(
                f"Failed to cleanup sandbox for session {session_uuid}: {e}"
            )

    # ── Sandbox resolution ──────────────────────────────────────────────

    async def resolve_sandbox_for_session(
        self, db: AsyncSession, session_id: uuid.UUID, *, session_service
    ) -> Sandbox | None:
        """Resolve the sandbox record for a session, handling forked sessions.

        Tries to find a sandbox directly by *session_id*.  If none is found,
        falls back to the session's ``sandbox_id`` (set when a forked session
        shares a parent sandbox).

        Args:
            db: Active database session.
            session_id: The session UUID to look up.
            session_service: A ``SessionService`` instance (passed to avoid
                circular imports).

        Returns:
            The :class:`Sandbox` record, or ``None`` if no sandbox exists.
        """
        # Direct lookup by session_id
        sandbox_record = await self._repo.get_by_session_id(db, str(session_id))

        if sandbox_record:
            return sandbox_record

        # Fallback: check if the session has a shared sandbox_id (forked sessions)
        session = await session_service.get_session_by_id(db, session_id=session_id)
        if session and session.sandbox_id:
            sandbox_record = await self._repo.get_by_id(
                db, uuid.UUID(str(session.sandbox_id))
            )
        return sandbox_record

    # ── Pure DB CRUD ───────────────────────────────────────────────────

    async def get_by_id(
        self, db: AsyncSession, sandbox_id: uuid.UUID
    ) -> Sandbox | None:
        return await self._repo.get_by_id(db, sandbox_id)

    async def get_by_session_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Sandbox | None:
        return await self._repo.get_by_session_id(db, str(session_id))

    async def get_by_provider_id(
        self, db: AsyncSession, provider_sandbox_id: str, provider: str = "e2b"
    ) -> Sandbox | None:
        return await self._repo.get_by_provider_id(
            db, provider_sandbox_id, provider
        )


__all__ = ["SandboxService"]
