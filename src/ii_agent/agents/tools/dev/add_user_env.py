import uuid
from typing import TYPE_CHECKING, Any

from ii_agent.agents.tools.base import BaseAgentTool, ToolResult
from ii_agent.core.container import get_app_container
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.projects.databases.models import ProjectDatabase
from ii_agent.projects.databases.repository import ProjectDatabaseRepository
from ii_agent.projects.databases.types import DatabaseSource
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.repository import ProjectRepository
from ii_agent.projects.secrets.service import SecretService

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

NAME = "add_user_env"
DISPLAY_NAME = "Add User Environment Variables"
DESCRIPTION = """Adds secrets to the project's environment files (.env, /app/.user_env.sh).

Usage:
- Run this after initializing a project to configure environment variables (API keys, tokens, etc.).
- Provide the project directory and the list of secrets with their values.
- Secrets are saved to the project database and written to environment files.

Each secret must include `key` and `value`. Optionally include a `description`.
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_directory": {
            "type": "string",
            "description": "Absolute or workspace-relative path to the project root.",
        },
        "secrets": {
            "type": "array",
            "description": "List of secrets to add as environment variables.",
            "items": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Environment variable name (e.g., OPENAI_API_KEY).",
                    },
                    "value": {
                        "type": "string",
                        "description": "The secret value.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional explanation for how the secret is used.",
                    },
                },
                "required": ["key", "value"],
            },
        },
    },
    "required": ["project_directory", "secrets"],
}


class AddUserEnvTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
    requires_sandbox = False

    def __init__(self) -> None:
        self._agent: "IIAgent | None" = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        self._agent = agent

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        project_dir = tool_input.get("project_directory", "")
        secrets = tool_input.get("secrets", [])

        secrets_dict = {}
        for secret in secrets:
            if not isinstance(secret, dict):
                continue
            key = secret.get("key")
            value = secret.get("value")
            if key and value is not None:
                secrets_dict[key] = value

        if not secrets_dict:
            return ToolResult(
                llm_content="No valid secrets provided (each must have key and value).",
                is_error=True,
            )

        session_id = getattr(self._agent, "session_id", None)
        user_id = getattr(self._agent, "user_id", None)
        if not session_id:
            return ToolResult(
                llm_content="No active session found for add_user_env.",
                user_display_content="No active session found.",
                is_error=True,
            )

        session_uuid = (
            session_id if isinstance(session_id, uuid.UUID) else uuid.UUID(str(session_id))
        )

        try:
            container = get_app_container()

            if not user_id:
                async with get_db_session_local() as db:
                    session_obj = await container.session_service.get_session_by_id(
                        db, session_uuid
                    )
                    if session_obj:
                        user_id = str(session_obj.user_id)
            if not user_id:
                return ToolResult(
                    llm_content="Project owner could not be resolved for this session.",
                    user_display_content="Session user not found.",
                    is_error=True,
                )

            user_uuid = (
                user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
            )

            # Sync DATABASE_URL to ProjectDatabases table if provided
            database_url = secrets_dict.get("DATABASE_URL")
            if database_url and isinstance(database_url, str):
                db_repo = ProjectDatabaseRepository()
                async with get_db_session_local() as db:
                    existing = await db_repo.get_active_by_session_id(db, session_uuid)
                    if existing:
                        existing.connection_string = database_url
                        existing.source = DatabaseSource.USER
                    else:
                        new_record = ProjectDatabase(
                            session_id=session_uuid,
                            source=DatabaseSource.USER,
                            connection_string=database_url,
                        )
                        await db_repo.save(db, new_record)
                    await db.commit()

            # Save secrets to project via SecretService
            secret_svc = SecretService(
                project_repo=ProjectRepository(),
                config=container.config,
            )
            async with get_db_session_local() as db:
                project = await secret_svc.add_secrets(
                    db,
                    session_id=session_uuid,
                    user_id=user_uuid,
                    secrets=secrets_dict,
                )
                await db.commit()

            synced = True

            return ToolResult(
                llm_content=(
                    f"Added {len(secrets_dict)} secret(s) to {project_dir or project.project_path}."
                ),
                user_display_content={
                    "project_directory": project_dir or project.project_path,
                    "secrets": {key: "***" for key in secrets_dict.keys()},
                    "keys": list(secrets_dict.keys()),
                    "synced_to_sandbox": synced,
                },
                is_error=False,
            )
        except ProjectNotFoundError:
            return ToolResult(
                llm_content=(
                    "Project is not initialized; initialize a project before adding secrets."
                ),
                user_display_content="Project is not initialized",
                is_error=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"AddUserEnvTool: Failed to add secrets: {exc}")
            return ToolResult(
                llm_content=f"Failed to add secrets: {exc}",
                user_display_content=f"Failed to add secrets: {exc}",
                is_error=True,
            )
