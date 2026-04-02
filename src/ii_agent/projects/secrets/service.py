"""Service for managing project secrets - DB persistence only."""

from __future__ import annotations

import uuid
from typing import Any, Dict, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings

from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.secrets.utils import _decrypt_secrets_payload, _encrypt_secrets_payload

if TYPE_CHECKING:
    from ii_agent.projects.models import Project


class SecretService:
    """Service for saving secrets to DB.

    Sandbox env file syncing is handled separately by
    ``sandboxes.env_sync_service.SandboxEnvSyncService``.
    """

    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._project_repo = project_repo

    async def replace_session_project_secrets(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        secrets: Dict[str, Any],
    ) -> "Project":
        """Replace the session project secrets."""
        project = await self._project_repo.get_by_session_and_user(
            db, session_id=session_id, user_id=user_id
        )
        if not project:
            raise ProjectNotFoundError(
                f"Project for session {session_id} not found or access denied"
            )

        project.secrets_json = _encrypt_secrets_payload(secrets)
        return await self._project_repo.update(db, project)

    async def get_session_project(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> "Project":
        """Fetch the session project for a user."""
        project = await self._project_repo.get_by_session_and_user(
            db, session_id=session_id, user_id=user_id
        )
        if not project:
            raise ProjectNotFoundError(
                f"Project for session {session_id} not found or access denied"
            )
        return project

    async def add_secrets(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        secrets: Dict[str, Any],
    ) -> "Project":
        """Add or overwrite secrets for a session project without removing existing values."""
        project = await self.get_session_project(
            db,
            session_id=session_id,
            user_id=user_id,
        )

        existing_secrets = _decrypt_secrets_payload(project.secrets_json) or {}
        if not isinstance(existing_secrets, dict):
            existing_secrets = {}

        merged = {**existing_secrets, **secrets}

        return await self.replace_session_project_secrets(
            db,
            session_id=session_id,
            user_id=user_id,
            secrets=merged,
        )

    async def delete_secrets(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        secret_keys: list[str],
    ) -> "Project":
        """Delete specific secrets for a session project."""
        if not secret_keys:
            return await self.get_session_project(
                db,
                session_id=session_id,
                user_id=user_id,
            )

        project = await self.get_session_project(
            db,
            session_id=session_id,
            user_id=user_id,
        )

        existing_secrets = _decrypt_secrets_payload(project.secrets_json) or {}
        if not isinstance(existing_secrets, dict):
            existing_secrets = {}

        for key in secret_keys:
            existing_secrets.pop(key, None)

        return await self.replace_session_project_secrets(
            db,
            session_id=session_id,
            user_id=user_id,
            secrets=existing_secrets,
        )
