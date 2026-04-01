from ii_agent.agents.factory.mcp.base import MCPTool


class BrowserEnterMultipleTextsTool(MCPTool):
    name = "browser_enter_multi_texts"
    display_name = "Browser Enter Multiple Texts"
    description = """Enter text on multiple input fields in sequence with a single call. Useful for filling forms like login (username + password), registration (name + email + password), or any multi-field form. 

Examples:
- Login form: Fill username at (300, 200) and password at (300, 250)
- Registration: Fill name at (200, 150), email at (200, 200), password at (200, 250)
- Contact form: Fill name, email, phone number, and message fields
- Profile update: Fill multiple profile fields like first name, last name, phone, address

Each field will be clicked and filled sequentially in the order provided."""
    input_schema = {
        "type": "object",
        "properties": {
            "enter_texts": {
                "type": "array",
                "description": "List of text entries to input on different fields",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to enter"},
                        "coordinate_x": {
                            "type": "number",
                            "description": "X coordinate to click before entering text",
                        },
                        "coordinate_y": {
                            "type": "number",
                            "description": "Y coordinate to click before entering text",
                        },
                        "press_enter": {
                            "type": "boolean",
                            "description": "If True, press Enter after entering this text. Default is False.",
                            "default": False,
                        },
                        "override": {
                            "type": "boolean",
                            "description": "If True, the current text in the element will be cleared before entering new text. If False, the new text will be appended to the existing text. Default is False.",
                            "default": False,
                        },
                    },
                    "required": ["text", "coordinate_x", "coordinate_y"],
                },
                "minItems": 1,
            },
        },
        "required": ["enter_texts"],
    }
    read_only = False
