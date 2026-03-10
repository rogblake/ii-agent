from typing import Any, Dict

from ii_agent.engine.runtime.tools.base import BaseAgentTool, ToolResult

# Name
NAME = "web_visit"
DISPLAY_NAME = "Web Visit"

# Tool description
DESCRIPTION = """Retrieves and extracts the text content of a given webpage URL. It is useful when you need to extract information from a webpage after discovering it through search results

When to Use:
- Access the full content of an article, documentation page, or blog post
- Gather detailed information from a specific source URL
- Use after web_search tool to dive deeper into a chosen result
- Extract specific information from a webpage using a prompt (e.g., "Extract the main pricing tiers" or "Summarize the key features")

NOTE: Prefer using prompt to get focused, relevant information instead of processing large raw content
"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "The URL of the webpage to visit and extract content from",
        },
        "prompt": {
            "type": "string",
            "description": "The prompt to run on the content of the webpage. If provided, processes the webpage content with this prompt to extract specific information. If not provided, returns the raw extracted content",
        },
    },
    "required": ["url"],
}
FAILURE_MESSAGE = "Please try again. If the problem continues, switch to browser tools for manual visiting and let the user know that web visit is temporarily unavailable."


class WebVisitTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, credential: Dict | None = None, tool_server_url: str | None = None):
        super().__init__()
        self.credential = credential or {}

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        url = tool_input["url"]
        prompt = tool_input.get("prompt", None)
        if "arxiv.org/abs" in url:
            url = "https://arxiv.org/html/" + url.split("/")[-1]

        try:
            response = await self.dependencies.tool_client.web_visit(url, prompt)
            content = response.content
        except Exception as exc:
            return ToolResult(
                llm_content=f"The visit request failed: {exc}. {FAILURE_MESSAGE}",
                is_error=True,
            )

        if content is None or (isinstance(content, str) and not content.strip()):
            return ToolResult(
                llm_content="The webpage content is empty or un-extractable (e.g. login, paywall, etc.). Please try again with a different URL or use browser tools to visit manually.",
                is_error=True,
            )

        return ToolResult(
            llm_content=content,
            cost=response.cost,
        )
