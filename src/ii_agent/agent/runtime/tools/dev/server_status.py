from ii_agent.agent.runtime.tools.mcp.base import MCPTool

NAME = "get_server_status"
DISPLAY_NAME = "Get server status"
DESCRIPTION = "Fetch the latest server log output and a screenshot of the current server view."
INPUT_SCHEMA = {"type": "object", "properties": {}, "required": []}


class GetServerStatusTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
