from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool

NAME = "BashStop"
DISPLAY_NAME = "Stop bash command or kill session"
DESCRIPTION = "Stop a running command in a bash session by sending a SIGINT signal (Ctrl+C), or kill the entire session."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to stop the command in or kill.",
        },
        "kill_session": {
            "type": "boolean",
            "description": "If true, kill the entire session. If false or not provided, only stop the current command.",
            "default": False,
        },
    },
    "required": ["session_name"],
}


class ShellStopCommand(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def execute(self, tool_input: dict) -> ToolResult:
        session_name = tool_input.get("session_name")
        kill_session = tool_input.get("kill_session", False)
        sandbox_service = self.get_sandbox_service()
        session_id = self.get_session_id()

        try:
            all_current_sessions = await sandbox_service.list_shell_sessions(session_id)
            if session_name not in all_current_sessions:
                return ToolResult(
                    llm_content=(
                        f"Session '{session_name}' is not available. "
                        f"Available sessions: {all_current_sessions}"
                    ),
                    is_error=True,
                )

            if kill_session:
                await sandbox_service.delete_shell_session(session_id, session_name)
                return ToolResult(
                    llm_content=f"Session '{session_name}' killed successfully.",
                    is_error=False,
                )

            result = await sandbox_service.kill_shell_command(
                session_id,
                session_name,
            )
            return ToolResult(
                llm_content=(
                    f"Current running command in session '{session_name}' stopped successfully. "
                    f"Current output:\n\n{result.clean_output}"
                ),
                user_display_content=(
                    f"Current running command in session '{session_name}' stopped successfully. "
                    f"Current output:\n\n{result.ansi_output}"
                ),
                is_error=False,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                llm_content=f"Error stopping session: {exc}",
                is_error=True,
            )
