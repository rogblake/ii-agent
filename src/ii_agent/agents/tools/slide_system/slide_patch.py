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

NAME = "slide_apply_patch"
DISPLAY_NAME = "Apply Slide Patch"
DESCRIPTION = """Use the `slide_apply_patch` tool to create or edit slides in presentations.

Your patch language follows this format:

*** Begin Slide Patch
[ one or more slide operations ]
*** End Slide Patch

Within that envelope, you can perform three types of operations:

*** Add Slide: <presentation_name>/<slide_number> - create a new slide
*** Update Slide: <presentation_name>/<slide_number> - patch an existing slide

For Add and Update operations, you can optionally include metadata:
*** Metadata:
Title: <slide title>
Description: <slide description>
Type: <slide type (cover, content, chart, conclusion, etc.)>

Examples:

1. Creating a new slide:
*** Begin Slide Patch
*** Add Slide: my_presentation/1
*** Metadata:
Title: Introduction
Description: Opening slide with title and agenda
Type: cover
+<!DOCTYPE html>
+<html lang="en">
+<head>
+    <meta charset="UTF-8">
+    <title>Introduction</title>
+</head>
+<body>
+    <h1>Welcome</h1>
+</body>
+</html>
*** End Slide Patch

2. Updating an existing slide:
*** Begin Slide Patch
*** Update Slide: my_presentation/2
*** Metadata:
Title: Updated Title
Description: Modified slide content
@@ <h1 class="title">
-    Old Title
+    New Title
*** End Slide Patch

3. Multiple operations:
*** Begin Slide Patch
*** Update Slide: workshop/1
@@ <title>
-Workshop Introduction
+Advanced Workshop Introduction
*** Add Slide: workshop/5
*** Metadata:
Title: Conclusion
Description: Final slide with summary
Type: conclusion
+<!DOCTYPE html>
+<html>
+<body>
+    <h1>Thank You!</h1>
+</body>
+</html>
*** End Slide Patch

Important notes:
- Presentation names and slide numbers are specified as: presentation_name/slide_number
- Slide numbers are 1-based (slide 1, not slide 0)
- When updating slides, use context lines (with spaces) to uniquely identify the location
- For HTML content, ensure proper formatting and structure
- All local file paths in HTML must be absolute paths accessible by the agent
- The tool automatically updates metadata.json timestamps
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "description": "The slide_apply_patch command that you wish to execute.",
        }
    },
    "required": ["input"],
}


class SlideApplyPatchTool(MCPTool):
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
