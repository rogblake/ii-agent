from ii_agent.engine.runtime.tools.mcp.base import MCPTool


class BrowserEnterTextTool(MCPTool):
    name = "browser_enter_text"
    display_name = "Browser Enter Text"
    description = "Enter text with a keyboard. If coordinates are provided, will click on that position first before entering text."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to enter with a keyboard."},
            "coordinate_x": {
                "type": "number",
                "description": "Optional X coordinate to click before entering text",
            },
            "coordinate_y": {
                "type": "number",
                "description": "Optional Y coordinate to click before entering text",
            },
            "press_enter": {
                "type": "boolean",
                "description": "If True, `Enter` button will be pressed after entering the text. Use this when you think it would make sense to press `Enter` after entering the text, such as when you're submitting a form, performing a search, etc.",
                "default": False,
            },
            "override": {
                "type": "boolean",
                "description": "If True, the current text in the element will be cleared before entering new text. If False, the new text will be appended to the existing text. Default is False.",
                "default": False,
            },
        },
        "required": ["text"],
    }
    read_only = False
