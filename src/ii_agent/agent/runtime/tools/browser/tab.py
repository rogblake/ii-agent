from ii_agent.agent.runtime.tools.mcp.base import MCPTool


class BrowserSwitchTabTool(MCPTool):
    name = "browser_switch_tab"
    display_name = "Browser Switch Tab"
    description = "Switch to a specific tab by tab index"
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the tab to switch to.",
            }
        },
        "required": ["index"],
    }
    read_only = False


class BrowserOpenNewTabTool(MCPTool):
    name = "browser_open_new_tab"
    display_name = "Browser Open New Tab"
    description = "Open a new tab"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False
