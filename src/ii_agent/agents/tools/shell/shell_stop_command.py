from ii_agent.agents.factory.mcp.base import MCPTool

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


class ShellStopCommand(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
