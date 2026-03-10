from ii_agent.agent.runtime.tools.mcp.base import MCPTool


class BrowserNavigationTool(MCPTool):
    name = "browser_navigation"
    display_name = "Browser Navigation"
    description = "Navigate browser to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }
    read_only = False


class BrowserRestartTool(MCPTool):
    name = "browser_restart"
    display_name = "Browser Restart"
    description = "Restart browser and navigate to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }
    read_only = False
