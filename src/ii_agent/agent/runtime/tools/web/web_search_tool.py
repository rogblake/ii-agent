import json
from typing import Any

from ii_agent.agent.runtime.tools.base import BaseAgentTool, ToolResult


# Name
NAME = "web_search"
DISPLAY_NAME = "Web Search"

# Tool description
DESCRIPTION = """Performs a web search using a search engine API and returns the top 5 results with each result's title, URL, and snippet. 

When to Use
- Find information on the internet that goes beyond the model's training cutoff
- Research current events, documentation, tutorials, or updates
- Check the latest news and trends

Combine with the web_visit tool to open a result's URL and extract its full content.
"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query to find information on the web",
        },
    },
    "required": ["query"],
}

MAX_RESULTS = 12
FAILURE_MESSAGE = "Please try again. If the problem continues, activate the `agent-browser` skill for manual searching and let the user know that web search is temporarily unavailable."
DEFAULT_WEB_SEARCH_MAX_COST_USD = 0.05


class WebSearchTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
    max_cost_usd = DEFAULT_WEB_SEARCH_MAX_COST_USD

    def __init__(self):
        super().__init__()

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        query = tool_input["query"]

        try:
            response = await self.dependencies.tool_client.web_search(
                query, max_results=MAX_RESULTS
            )
            results = response.result[:MAX_RESULTS]
        except Exception as exc:
            return ToolResult(
                llm_content=f"The search request failed: {exc}. {FAILURE_MESSAGE}",
                is_error=True,
            )

        results_str = json.dumps(results, indent=2)

        if len(results) == 0:
            return ToolResult(
                llm_content=f"The search engine processed your query '{query}' successfully but found no matching results. Try rephrasing with different keywords, broader terms, or check for typos.",
                user_display_content=results_str,  # NOTE: to compatible with the current frontend implementation
                is_error=False,
                cost=response.cost,
            )

        return ToolResult(
            llm_content=results_str,
            is_error=False,
            cost=response.cost,
        )
