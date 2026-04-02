from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.agents.sandboxes.shell import (
    ShellInvalidSessionNameError,
    ShellOperationError,
    ShellRunDirNotFoundError,
    ShellSessionExistsError,
)
from ii_agent.core.config.settings import get_settings

NAME = "BashInit"
DISPLAY_NAME = "Initialize bash session"
DESCRIPTION = """Initialize a persistent bash shell session for command execution.
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to initialize.",
        },
        "start_directory": {
            "type": "string",
            "description": "The absolute path to a directory to start the session in. If not provided, the session will start in the workspace directory.",
        },
    },
    "required": ["session_name"],
}


class ShellInit(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def execute(self, tool_input: dict) -> ToolResult:
        session_name = tool_input.get("session_name")
        start_directory = tool_input.get("start_directory")
        sandbox_service = self.get_sandbox_service()
        session_id = self.get_session_id()

        try:
            all_current_sessions = await sandbox_service.list_shell_sessions(session_id)
            if session_name in all_current_sessions:
                return ToolResult(
                    llm_content=f"Session '{session_name}' already exists",
                    is_error=True,
                )

            if not start_directory:
                start_directory = get_settings().workspace_path

            await sandbox_service.create_shell_session(
                session_id,
                session_name,
                start_directory,
            )
            return ToolResult(
                llm_content=(
                    f"Session '{session_name}' initialized successfully at start directory "
                    f"`{start_directory}`"
                ),
                is_error=False,
            )
        except (
            ShellInvalidSessionNameError,
            ShellOperationError,
            ShellRunDirNotFoundError,
            ShellSessionExistsError,
        ) as exc:
            return ToolResult(
                llm_content=f"Error initializing session: {exc}",
                is_error=True,
            )
