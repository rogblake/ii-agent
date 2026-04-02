from typing import Any

from ii_agent.agents.tools.base import BaseAgentTool, ToolResult

NAME = "ask_user_select"
DISPLAY_NAME = "Ask User to Select"
DESCRIPTION = """Present a question with options to the user and wait for their selection.

Use this tool when you need the user to make a choice before proceeding. The agent will pause
and display the question with the provided options. The user selects one option, and the agent
resumes with the selected value.

Examples:
- Ask which database provider to use (default vs supabase) before initializing a project
- Ask which deployment target to use
- Ask the user to confirm a choice between multiple approaches

Parameters:
- question: The question to display to the user
- options: A list of option objects, each with a "value" (returned to agent) and "label" (displayed to user)
- selected: The option value selected by the user (filled by the user, leave empty when calling)
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "The question to present to the user.",
        },
        "options": {
            "type": "array",
            "description": "List of options for the user to choose from.",
            "items": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "The value returned to the agent when this option is selected.",
                    },
                    "label": {
                        "type": "string",
                        "description": "The human-readable label displayed to the user.",
                    },
                },
                "required": ["value", "label"],
            },
        },
        "selected": {
            "type": "string",
            "description": "The selected option value. Leave empty when calling - the user will fill this in.",
        },
    },
    "required": ["question", "options", "selected"],
}


class AskUserSelectTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
    requires_confirmation = False
    requires_user_input = True
    user_input_fields = ["selected"]
    requires_sandbox = False

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        question = tool_input.get("question", "")
        options = tool_input.get("options", [])
        selected = tool_input.get("selected", "")

        valid_values = [opt.get("value") for opt in options if isinstance(opt, dict)]
        if selected and selected not in valid_values:
            return ToolResult(
                llm_content=f"Invalid selection '{selected}'. Valid options are: {valid_values}",
                user_display_content=f"Invalid selection: {selected}",
                is_error=True,
            )

        selected_label = selected
        for opt in options:
            if isinstance(opt, dict) and opt.get("value") == selected:
                selected_label = opt.get("label", selected)
                break

        return ToolResult(
            llm_content=f'User was asked: "{question}"\nUser selected: "{selected}" ({selected_label})',
            user_display_content={
                "question": question,
                "selected": selected,
                "selected_label": selected_label,
            },
            is_error=False,
        )
