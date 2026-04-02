from ii_agent.engine.v1.tools.mcp.base import MCPTool

NAME = "restart_fullstack_servers"
DISPLAY_NAME = "Restart dev servers"
DESCRIPTION = (
    "Stops and restarts development servers using metadata recorded during project initialization."
)
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}


class RestartServerTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
