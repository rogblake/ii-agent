from ii_agent.agents.factory.mcp.base import MCPTool


class BrowserWaitTool(MCPTool):
    name = "browser_wait"
    display_name = "Browser Wait"
    description = "Wait for the page to load"
    input_schema = {"type": "object", "properties": {}}
    read_only = False
