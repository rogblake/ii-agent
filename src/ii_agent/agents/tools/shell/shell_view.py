from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool

NAME = "BashView"
DISPLAY_NAME = "View bash session output"
DESCRIPTION = "View the current output of bash sessions."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "An array of session names to view the output of.",
        }
    },
    "required": ["session_names"],
}


class ShellView(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    async def execute(self, tool_input: dict) -> ToolResult:
        session_names = tool_input.get("session_names", [])
        sandbox_service = self.get_sandbox_service()
        session_id = self.get_session_id()

        try:
            all_current_sessions = await sandbox_service.list_shell_sessions(session_id)

            for session_name in session_names:
                if session_name not in all_current_sessions:
                    return ToolResult(
                        llm_content=(
                            f"Session '{session_name}' is not initialized. "
                            f"Available sessions: {all_current_sessions}"
                        ),
                        is_error=True,
                    )

            ansi_result = "Current output of:\n\n"
            clean_result = "Current output of:\n\n"

            for session_name in session_names:
                session_output = await sandbox_service.get_shell_session_output(
                    session_id,
                    session_name,
                )
                ansi_result += f"Session: {session_name}\n{session_output.ansi_output}\n"
                ansi_result += "---\n"
                clean_result += f"Session: {session_name}\n{session_output.clean_output}\n"
                clean_result += "---\n"

            return ToolResult(
                llm_content=clean_result,
                user_display_content=ansi_result,
                is_error=False,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                llm_content=f"Error viewing session output: {exc}",
                is_error=True,
            )
