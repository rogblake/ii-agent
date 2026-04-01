from ii_agent.agents.factory.mcp.base import MCPTool

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


class ShellView(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
