from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool

NAME = "BashWriteToProcess"
DISPLAY_NAME = "Write to shell process"
DESCRIPTION = """Write to a process in a specified shell session. Use for interacting with running processes."""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to write to",
        },
        "input": {
            "type": "string",
            "description": "Text to write to the process",
        },
        "press_enter": {
            "type": "boolean",
            "description": "Whether to press enter after writing the text",
            "default": True,
        },
    },
    "required": ["session_name", "input"],
}


class ShellWriteToProcessTool(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def execute(self, tool_input: dict) -> ToolResult:
        session_name = tool_input.get("session_name")
        input_text = tool_input.get("input")
        press_enter = tool_input.get("press_enter", True)
        sandbox_service = self.get_sandbox_service()
        session_id = self.get_session_id()

        if not input_text:
            return ToolResult(llm_content="input is required", is_error=True)

        try:
            all_current_sessions = await sandbox_service.list_shell_sessions(session_id)
            if session_name not in all_current_sessions:
                return ToolResult(
                    llm_content=(
                        f"Session '{session_name}' is not initialized. "
                        f"Use `ShellInit` to initialize a session. Available sessions: {all_current_sessions}"
                    ),
                    is_error=True,
                )

            result = await sandbox_service.write_to_shell_process(
                session_id,
                session_name,
                input_text,
                press_enter,
            )
            return ToolResult(
                llm_content=result.clean_output,
                user_display_content=result.ansi_output,
                is_error=False,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                llm_content=f"Error writing to session: {exc}",
                is_error=True,
            )
