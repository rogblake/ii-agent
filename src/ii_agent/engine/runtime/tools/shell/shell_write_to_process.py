from ii_agent.engine.runtime.tools.mcp.base import MCPTool

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


class ShellWriteToProcessTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
