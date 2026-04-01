"""Save a validated checkpoint for a local web project."""

from __future__ import annotations

import json
import logging
import shlex
from typing import TYPE_CHECKING, Any

from ii_agent.agents.tools.base import TextContent, ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

logger = logging.getLogger(__name__)

NAME = "save_checkpoint"
DISPLAY_NAME = "Save checkpoint"
DESCRIPTION = (
    "Save a checkpoint of the work the agents have done. This must be called after the user's task is done, or after a major change have been implemented."
    "Always call this tool when you have done testing and ensure the required functionalities are implemented"
)
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_directory": {
            "type": "string",
            "description": "Absolute or workspace-relative path to the project root.",
        },
        "commit_message": {
            "type": "string",
            "description": "git commit message (default: 'Checkpoint').",
        },
    },
    "required": ["project_directory", "commit_message"],
}

DEFAULT_TIMEOUT = 1800


class SaveCheckpointTool(BaseSandboxTool):
    """Run the bundled ii-app checkpoint flow inside the sandbox."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        project_directory = str(tool_input["project_directory"])
        commit_message = str(tool_input["commit_message"])

        cmd_parts = [
            "ii-app",
            "web",
            "checkpoint",
            "--workspace",
            "/workspace",
            "--project-directory",
            project_directory,
            "--commit-message",
            commit_message,
            "--json",
        ]
        cmd = " ".join(shlex.quote(part) for part in cmd_parts)

        try:
            output = await self.sandbox.run_command(cmd, timeout=DEFAULT_TIMEOUT)
            result = json.loads(output)
            return ToolResult(
                llm_content=[TextContent(type="text", text=output)],
                user_display_content=result,
            )
        except Exception as exc:
            logger.exception("Failed to save checkpoint")
            message = f"Failed to save checkpoint: {exc}"
            return ToolResult(
                llm_content=message,
                user_display_content=message,
                is_error=True,
            )
