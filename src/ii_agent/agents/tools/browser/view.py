from ii_agent.agents.factory.mcp.base import MCPTool


class BrowserViewTool(MCPTool):
    name = "browser_view_interactive_elements"
    display_name = "Browser View Interactive Elements"
    description = "Return the visible interactive elements on the current page"
    input_schema = {"type": "object", "properties": {}}
    read_only = False
