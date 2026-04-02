import json
from typing import Any

from ii_agent.engine.v1.tools.base import BaseAgentTool, ToolResult


# Name
NAME = "web_batch_search"
DISPLAY_NAME = "Web Batch Search"

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
        "queries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The search queries to find information on the web",
        },
    },
    "required": ["queries"],
}

MAX_RESULTS = 6
FAILURE_MESSAGE = "Please try again. If the problem continues, switch to browser tools for manual searching and let the user know that web search is temporarily unavailable."


class WebBatchSearchTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self):
        super().__init__()

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        queries = tool_input["queries"]

        try:
            response = await self.dependencies.tool_client.web_batch_search(queries, max_results=MAX_RESULTS)
            results = [result.result[:MAX_RESULTS] for result in response]
        except Exception as exc:
            return ToolResult(
                llm_content=f"The search request failed: {exc}. {FAILURE_MESSAGE}",
                is_error=True,
            )
        result_str = ""
        for i, query in enumerate(queries):
            result_str += f"Query: {query}\n"
            for j, result in enumerate(results[i] if i < len(results) else []):
                result_str += f"Output {j + 1}:\n"
                result_str += f"Title: {result.get('title', '')}\n"
                result_str += f"URL: {result.get('url', '')}\n"
                result_str += f"Snippet: {result.get('content', '')}\n"
                result_str += "-----------------------------------\n"

        if len(results) == 0:
            return ToolResult(
                llm_content=f"The search engine processed your query '{queries}' successfully but found no matching results. Try rephrasing with different keywords, broader terms, or check for typos.",
                user_display_content="",  # NOTE: to compatible with the current frontend implementation
                is_error=False,
                cost=sum(r.cost for r in response),
            )

        user_display_results = []
        for result in results:
            user_display_results.extend(result)

        return ToolResult(
            llm_content=result_str,
            user_display_content=json.dumps(user_display_results, indent=2),
            is_error=False,
            cost=sum(r.cost for r in response),
        )
