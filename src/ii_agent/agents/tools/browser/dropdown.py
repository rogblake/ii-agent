from ii_agent.agents.factory.mcp.base import MCPTool


class BrowserGetSelectOptionsTool(MCPTool):
    name = "browser_get_select_options"
    display_name = "Browser Get Select Options"
    description = "Get all options from a <select> element. Use this action when you need to get all options from a dropdown."
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the <select> element to get options from.",
            }
        },
        "required": ["index"],
    }
    read_only = False


class BrowserSelectDropdownOptionTool(MCPTool):
    name = "browser_select_dropdown_option"
    display_name = "Browser Select Dropdown Option"
    description = "Select an option from a <select> element by the text (name) of the option. Use this after get_select_options and when you need to select an option from a dropdown."
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the <select> element to select an option from.",
            },
            "option": {
                "type": "string",
                "description": "Text (name) of the option to select from the dropdown.",
            },
        },
        "required": ["index", "option"],
    }
    read_only = False
