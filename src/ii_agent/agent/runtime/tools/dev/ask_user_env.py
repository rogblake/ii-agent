from typing import TYPE_CHECKING, Any

from ii_agent.agent.runtime.tools.base import BaseAgentTool, ToolResult
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.projects.exceptions import ProjectNotFoundError

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

NAME = "ask_user_env"
DISPLAY_NAME = "Ask User for Environment Variables"
DESCRIPTION = """Requests environment variables or secrets from the user via a UI prompt.

Usage:
- Call this tool when the project needs API keys, tokens, or other secrets that the user must provide.
- The agent loop pauses before execution and the frontend shows a secrets input form.
- The frontend saves the secrets and syncs env files before resuming the run.
- After resume, this tool returns a success acknowledgement only.

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


class AskUserEnvTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
    requires_confirmation = True
    requires_sandbox = False

    def __init__(self) -> None:
        self._agent: "IIAgent | None" = None

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        self._agent = agent

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        project_dir = tool_input.get("project_directory", "")
        requested_keys = tool_input.get("requested_keys", [])
        message = tool_input.get("message")

        keys_list = [
            item.get("key")
            for item in requested_keys
            if isinstance(item, dict) and isinstance(item.get("key"), str) and item.get("key")
        ]

        session_id = getattr(self._agent, "session_id", None)
        user_id = getattr(self._agent, "user_id", None)

        if not session_id:
            return ToolResult(
                llm_content="No active session found for ask_user_env.",
                user_display_content="No active session found.",
                is_error=True,
            )

        try:
            async with get_db_session_local() as db:
                if not user_id:
                    user_id = await self.dependencies.session_service.get_session_user_id(
                        db,
                        str(session_id),
                    )
                if not user_id:
                    return ToolResult(
                        llm_content="Project owner could not be resolved for this session.",
                        user_display_content="Session user not found.",
                        is_error=True,
                    )

                project = await self.dependencies.project_service.get_session_project(
                    db,
                    session_id=str(session_id),
                    user_id=str(user_id),
                )
        except ProjectNotFoundError:
            return ToolResult(
                llm_content=(
                    "Project is not initialized; initialize a project before asking for "
                    "environment variables."
                ),
                user_display_content="Project is not initialized",
                is_error=True,
            )
        except Exception as exc:
            logger.warning(
                f"AskUserEnvTool: Failed to resolve project for session {session_id}: {exc}"
            )
            return ToolResult(
                llm_content=f"Failed to verify project before saving env vars: {exc}",
                user_display_content=f"Failed to verify project before saving env vars: {exc}",
                is_error=True,
            )

        project_path = project_dir or project.project_path
        key_list_display = ", ".join(keys_list) if keys_list else "requested environment variables"

        return ToolResult(
            llm_content=(
                f"Environment variables were saved for `{project_path}`. "
                f"Saved keys: {key_list_display}."
            ),
            user_display_content={
                "project_directory": project_path,
                "keys": keys_list,
                "message": message,
            },
            is_error=False,
        )
