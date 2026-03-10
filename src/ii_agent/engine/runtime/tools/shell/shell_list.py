from ii_agent.engine.runtime.tools.mcp.base import MCPTool

NAME = "BashList"
DISPLAY_NAME = "List bash sessions"
DESCRIPTION = "List all available bash sessions"
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}


class ShellList(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
