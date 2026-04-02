"""Web search tool - delegates to IIToolClient."""

import json

from ii_agent_tools.client import IIToolClient

from ii_agent.chat.types import ErrorTextContent, TextResultContent

from .base import BaseTool, ToolInfo, ToolCallInput, ToolResponse

MAX_RESULTS = 12


class WebSearchTool(BaseTool):
    """Search the web using IIToolClient."""

    max_cost_usd = 0.05

    def __init__(self, tool_client: IIToolClient):
        self.tool_client = tool_client
        self._name = "web_search"

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="web_search",
            description=(
                "Performs a web search using a search engine API and returns the top 5 results "
                "with each result's title, URL, and snippet. Use this to find information on the "
                "internet that goes beyond the model's training cutoff, research current events, "
                "documentation, tutorials, or check the latest news and trends."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find information on the web",
                    }
                },
            },
            required=["query"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        try:
            params = json.loads(tool_call.input)
            query = params["query"]
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        try:
            response = await self.tool_client.web_search(query, max_results=MAX_RESULTS)
            results = response.result[:MAX_RESULTS]
            cost = response.cost or 0.0

            if len(results) == 0:
                return ToolResponse(
                    output=TextResultContent(
                        value=(
                            f"The search engine processed your query '{query}' successfully "
                            "but found no matching results. Try rephrasing with different "
                            "keywords, broader terms, or check for typos."
                        )
                    ),
                    cost_usd=cost,
                )

            return ToolResponse(
                output=TextResultContent(value=json.dumps(results, indent=2)),
                cost_usd=cost,
            )

        except Exception as e:
            return ToolResponse(output=ErrorTextContent(value=f"Web search failed: {str(e)}"))
