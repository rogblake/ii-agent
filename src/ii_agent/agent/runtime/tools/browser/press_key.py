from ii_agent.agent.runtime.tools.mcp.base import MCPTool


class BrowserPressKeyTool(MCPTool):
    name = "browser_press_key"
    display_name = "Browser Press Key"
    description = "Simulate key press in the current browser page"
    input_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter).",
            }
        },
        "required": ["key"],
    }
    read_only = False
