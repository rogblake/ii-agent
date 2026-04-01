from ii_agent.agents.factory.mcp.base import MCPTool

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


class ShellInit(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
