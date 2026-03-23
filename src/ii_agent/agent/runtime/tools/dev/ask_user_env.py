from typing import TYPE_CHECKING, Any
from ii_agent.agent.runtime.tools.mcp.base import MCPTool
from ii_agent.agent.runtime.tools.base import ToolResult
from ii_agent.projects.exceptions import ProjectNotFoundError
from ii_agent.projects.databases.models import DatabaseSourceEnum
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

NAME = "ask_user_env"
DISPLAY_NAME = "Ask User for Environment Variables"
DESCRIPTION = """Requests environment variables or secrets from the user via a UI prompt.

Usage:
- Call this tool when the project needs API keys, tokens, or other secrets that the user must provide.
- The agent loop will pause and display a secrets input form to the user.
- Once the user provides the secrets, they will be saved to the project and written to environment files.

Each requested key should include:
- `key`: The environment variable name (e.g., OPENAI_API_KEY)
- `description`: A helpful description explaining what this key is used for
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_directory": {
            "type": "string",
            "description": "Absolute or workspace-relative path to the project root.",
        },
        "requested_keys": {
            "type": "array",
            "description": "List of environment variable keys to request from the user.",
            "items": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Environment variable name (e.g., OPENAI_API_KEY).",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of what this key is used for.",
                    },
                },
                "required": ["key"],
            },
        },
        "message": {
            "type": "string",
            "description": "Optional message to display to the user explaining why these secrets are needed.",
        },
    },
    "required": ["project_directory", "requested_keys"],
}


class AskUserEnvTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._agent: "IIAgent" = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)
        self._agent = agent

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute the tool, checking for project existence first."""
        # Check if project is initialized
        if self._agent:
            session_id = getattr(self._agent, "session_id", None)
            user_id = getattr(self._agent, "user_id", None)
            if session_id:
                try:
                    async with get_db_session_local() as db:
                        project = await self.dependencies.project_service.get_session_project(
                            db, session_id=str(session_id), user_id=str(user_id)
                        )
                    if not project:
                        return ToolResult(
                            llm_content="Project is not inited, you must init a project first before you can call this tool, ask the user for env again",
                            user_display_content="Project is not initialized",
                            is_error=True,
                        )
                except ProjectNotFoundError:
                    return ToolResult(
                        llm_content="Project is not inited, you must init a project first before you can call this tool, ask the user for env again",
                        user_display_content="Project is not initialized",
                        is_error=True,
                    )
                except Exception as exc:
                    logger.warning("AskUserEnvTool: Failed to check project: {}", exc)

        # Call parent execute
        return await super().execute(tool_input)

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
        secrets_payload = secrets if isinstance(secrets, dict) else None
        if secrets_payload and secrets_payload:
            user_display["secrets"] = {key: "***" for key in secrets_payload.keys()}
        elif "secrets" in user_display:
            user_display["secrets"] = "***"
        tool_result.user_display_content = user_display

        if not secrets_payload:
            return

        session_id = getattr(agent, "session_id", None)
        if not session_id:
            return

        user_id = getattr(agent, "user_id", None)
        if not user_id:
            async with get_db_session_local() as db:
                user_id = await self.dependencies.session_service.get_session_user_id(
                    db, str(session_id)
                )
            if not user_id:
                logger.warning("AskUserEnvTool: Session {} not found", session_id)
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
                "AskUserEnvTool: Saved {} secrets for session {}", len(secrets_payload), session_id
            )
        except ProjectNotFoundError:
            logger.warning("AskUserEnvTool: Project not found for session {}", session_id)
            return
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("AskUserEnvTool: Failed to save/sync secrets: {}", exc)
            return
