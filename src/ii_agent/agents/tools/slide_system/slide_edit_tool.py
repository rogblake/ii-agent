from typing import Any, Literal, TYPE_CHECKING
from ii_agent.agents.factory.mcp.base import MCPTool
from ii_agent.agents.tools.slide_system.hook_utils import (
    persist_slide_tool_result,
    process_slide_content,
)
from ii_agent.agents.tools.base import ToolResult
from ii_agent.core.container import get_app_container

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

NAME = "SlideEdit"
DISPLAY_NAME = "Edit slide"
DESCRIPTION = """Performs exact string replacements in slide HTML content.

Usage:
- Use this tool instead of FileEditTool for slide content
- Makes targeted string replacements in the slide's HTML content
- The edit will FAIL if old_string is not unique in the slide
- Use replace_all=True to replace all occurrences
- Local file paths in the HTML must be absolute paths accessible by the agent
- Automatically updates the metadata.json timestamp"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "presentation_name": {
            "type": "string",
            "description": "Name of the presentation",
        },
        "slide_number": {
            "type": "integer",
            "description": "Slide number to edit (1-based)",
            "minimum": 1,
        },
        "old_string": {"type": "string", "description": "Text to replace in the slide"},
        "new_string": {
            "type": "string",
            "description": "Replacement text (must be different from old_string)",
        },
        "replace_all": {
            "type": "boolean",
            "description": "Replace all occurrences (default false)",
            "default": False,
        },
        "update_description": {
            "type": "string",
            "description": "Optional: update the slide's description in metadata",
        },
    },
    "required": ["presentation_name", "slide_number", "old_string", "new_string"],
}


class SlideEditTool(MCPTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        input_schema: dict[str, Any],
        read_only: bool,
        requires_confirmation: bool,
        type: Literal["function", "openai_custom"] = "function",
    ) -> None:
        super().__init__(
            name=name,
            display_name=display_name,
            description=description,
            input_schema=input_schema,
            read_only=read_only,
            requires_confirmation=requires_confirmation,
            type=type,
        )
        self.url_cache = None

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        user_display = tool_result.user_display_content
        if user_display is None:
            return

        if self.url_cache is None:
            self.url_cache = {}

        processed_display = await process_slide_content(
            agent=agent,
            tool_name=self.name,
            user_display_content=user_display,
            url_cache=self.url_cache,
        )
        tool_result.user_display_content = processed_display

        await persist_slide_tool_result(
            agent=agent,
            slide_service=get_app_container().slide_service,
            tool_name=self.name,
            tool_input=fc.arguments or {},
            user_display_content=processed_display,
        )
