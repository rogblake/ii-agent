from ii_agent.engine.v1.tools.mcp.base import MCPTool


class BrowserScrollDownTool(MCPTool):
    name = "browser_scroll_down"
    display_name = "Browser Scroll Down"
    description = "Scroll down the current browser page"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False


class BrowserScrollUpTool(MCPTool):
    name = "browser_scroll_up"
    display_name = "Browser Scroll Up"
    description = "Scroll up the current browser page"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False
