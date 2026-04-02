from ii_agent.engine.v1.tools.mcp.base import MCPTool


class BrowserClickTool(MCPTool):
    name = "browser_click"
    display_name = "Browser Click"
    description = "Click on an element on the current browser page"
    input_schema = {
        "type": "object",
        "properties": {
            "coordinate_x": {
                "type": "number",
                "description": "X coordinate of click position",
            },
            "coordinate_y": {
                "type": "number",
                "description": "Y coordinate of click position",
            },
            "double_click": {
                "type": "boolean",
                "description": "If True, will perform a double click on the element",
                "default": False,
            },
        },
        "required": ["coordinate_x", "coordinate_y"],
    }
    read_only = False
