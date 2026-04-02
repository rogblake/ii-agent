from typing import TYPE_CHECKING
from ii_agent.projects.databases.models import DatabaseSourceEnum
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.engine.v1.tools.mcp.base import MCPTool
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.core.logger import logger
from ii_agent.engine.v1.tools.base import ToolResult

if TYPE_CHECKING:
    from ii_agent.engine.v1.agents.agent import IIAgent
    from ii_agent.engine.v1.tools.function import FunctionCall

NAME = "add_webdev_secrets"
DISPLAY_NAME = "Add WebDev secrets"
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


class AddWebDevSecrets(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        user_display = tool_result.user_display_content
        if not isinstance(user_display, dict):
            return

        secrets = user_display.get("secrets")
        project_directory = user_display.get("project_directory")

        secrets_payload = secrets if isinstance(secrets, dict) else None
        if secrets_payload and secrets_payload:
            user_display["secrets"] = {key: "***" for key in secrets_payload.keys()}
        elif "secrets" in user_display:
            user_display["secrets"] = "***"
        tool_result.user_display_content = user_display

        if not secrets_payload:
            logger.warning("AddWebDevSecrets: No secrets found in tool result")
            return

        session_id = getattr(agent, "session_id", None)
        if not session_id:
            return

        user_id = getattr(agent, "user_id", None)
        if not user_id:
            async with get_db_session_local() as db:
                user_id = await self.dependencies.session_service.get_session_user_id(db, str(session_id))
            if not user_id:
                logger.warning("AddWebDevSecrets: Session %s not found", session_id)
                return

        try:
            # Check if DATABASE_URL is in the secrets and sync to ProjectDatabases table
            database_url = secrets_payload.get("DATABASE_URL")
            if database_url and isinstance(database_url, str):
                from ii_agent.projects.databases.service import DatabaseService
                from ii_agent.projects.repository import ProjectRepository
                from ii_agent.core.config.settings import get_settings
                _db_service = DatabaseService(
                    project_repo=ProjectRepository(),
                    config=get_settings(),
                )
                async with get_db_session_local() as db:
                    await _db_service.upsert_database_from_url(
                        db,
                        session_id=str(session_id),
                        connection_string=database_url,
                        source=DatabaseSourceEnum.USER.value,
                    )
                logger.info(
                    "AddWebDevSecrets: Synced DATABASE_URL to ProjectDatabases for session %s",
                    session_id,
                )

            # Save secrets to project
            async with get_db_session_local() as db:
                project = await self.dependencies.project_service.get_session_project(
                    db, session_id=str(session_id), user_id=str(user_id)
                )
                existing_secrets = project.secrets_json or {}
                if not isinstance(existing_secrets, dict):
                    existing_secrets = {}
                existing_secrets.update(secrets_payload)
                project.secrets_json = existing_secrets
                await self.dependencies.project_service.update_session_project_secrets(
                    db,
                    project_id=project.id,
                    secrets=existing_secrets,
                )

            logger.info(
                "AddWebDevSecrets: Saved %s secrets for session %s",
                len(secrets_payload),
                session_id,
            )
        except ProjectNotFoundError:
            logger.warning("AddWebDevSecrets: Project not found for session %s", session_id)
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("AddWebDevSecrets: Failed to save/sync secrets: %s", exc)
            return
