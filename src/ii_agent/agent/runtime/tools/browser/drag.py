from ii_agent.agent.runtime.tools.mcp.base import MCPTool


class BrowserDragTool(MCPTool):
    name = "browser_drag"
    display_name = "Browser Drag"
    description = "Perform drag and drop between two elements"
    input_schema = {
        "type": "object",
        "properties": {
            "coordinate_x_start": {
                "type": "number",
                "description": "X coordinate of drag start position",
            },
            "coordinate_y_start": {
                "type": "number",
                "description": "Y coordinate of drag start position",
            },
            "coordinate_x_end": {
                "type": "number",
                "description": "X coordinate of drag end position",
            },
            "coordinate_y_end": {
                "type": "number",
                "description": "Y coordinate of drag end position",
            },
        },
        "required": [
            "coordinate_x_start",
            "coordinate_y_start",
            "coordinate_x_end",
            "coordinate_y_end",
        ],
    }
    read_only = False
