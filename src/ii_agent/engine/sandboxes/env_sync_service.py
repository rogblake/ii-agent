"""Service for syncing environment variables to sandbox .env and .user_env.sh files."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.logger import logger
from ii_agent.engine.sandboxes.e2b import E2BSandboxManager
from ii_agent.engine.sandboxes.repository import SandboxRepository
from ii_agent.sessions.repository import SessionRepository
from ii_agent.core.config.settings import Settings


class SandboxEnvSyncService:
    """Syncs environment variables to sandbox .env and .user_env.sh files.

    This service is responsible for writing env files into running sandboxes.
    It is decoupled from SecretService so that secret persistence (DB) and
    sandbox file sync are independent concerns.
    """

    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        sandbox_repo: SandboxRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._session_repo = session_repo
        self._sandbox_repo = sandbox_repo

    async def sync_env_files(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        secrets: Dict[str, Any],
        project_path: Optional[str] = None,
        database_url: Optional[str] = None,
    ) -> bool:
        """Update .env and .user_env.sh files in the sandbox with the provided secrets."""
        session = await self._session_repo.get_by_id(db, session_id)
        if not session or not session.sandbox_id:
            logger.warning(
                f"No sandbox_id available for session {session_id}, skipping env file update"
            )
            return False

        sandbox_record = await self._sandbox_repo.get_by_session_id(
            db, session_id=str(session_id)
        )
        if not sandbox_record:
            logger.warning(
                f"No sandbox_record available for session {session_id}, skipping env file update"
            )
            return False

        try:
            sandbox_manager = await E2BSandboxManager.connect(
                sandbox_id=str(session.sandbox_id),
                session_id=str(session_id),
                provider_sandbox_id=sandbox_record.provider_sandbox_id,
            )

            new_env_vars = dict(secrets)
            if database_url:
                new_env_vars["DATABASE_URL"] = database_url

            user_env_path = "/app/.user_env.sh"
            existing_vars = await self._read_user_env_sh(sandbox_manager, user_env_path)
            existing_vars.update(new_env_vars)
            merged_vars = existing_vars

            user_env_sh_content = _format_user_env_sh(merged_vars)
            await sandbox_manager.write_file(user_env_path, user_env_sh_content)
            logger.info(f"Updated {user_env_path} in sandbox {sandbox_record.id}")

            if project_path:
                env_file_path = f"{project_path}/.env"
                env_content = _format_env_file(merged_vars)
                await sandbox_manager.write_file(env_file_path, env_content)
                logger.info(f"Updated {env_file_path} in sandbox {session.sandbox_id}")

            return True

        except Exception as e:
            logger.error(
                f"Failed to update sandbox env files for session {session_id}: {e}"
            )
            return False

    async def _read_user_env_sh(
        self,
        sandbox_manager: E2BSandboxManager,
        file_path: str,
    ) -> Dict[str, Any]:
        """Read existing .user_env.sh file from sandbox and parse into dictionary."""
        existing_vars: Dict[str, Any] = {}
        try:
            content = await sandbox_manager.read_file(file_path)
            if content and isinstance(content, str):
                existing_vars = parse_user_env_sh(content)
        except Exception:
            pass
        return existing_vars


# ---------------------------------------------------------------------------
# Standalone formatting/parsing helpers
# ---------------------------------------------------------------------------


def parse_user_env_sh(content: str) -> Dict[str, str]:
    """Parse .user_env.sh file content into a dictionary."""
    result: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key:
                result[key] = value
    return result


def _format_env_file(secrets: Dict[str, Any]) -> str:
    """Format secrets as a .env file (KEY=VALUE format)."""
    lines = []
    for key, value in secrets.items():
        str_value = str(value) if value is not None else ""
        if "\n" in str_value or '"' in str_value or " " in str_value:
            str_value = '"' + str_value.replace('"', '\\"') + '"'
        lines.append(f"{key}={str_value}")
    return "\n".join(lines)


def _format_user_env_sh(secrets: Dict[str, Any]) -> str:
    """Format secrets as a shell script with exports (export KEY=VALUE format)."""
    lines = ["#!/bin/bash", "# User environment variables"]
    for key, value in secrets.items():
        str_value = str(value) if value is not None else ""
        str_value = '"' + str_value.replace('"', '\\"').replace("$", "\\$") + '"'
        lines.append(f"export {key}={str_value}")
    return "\n".join(lines)
