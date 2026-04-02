"""Image search tool - delegates to IIToolClient."""

import json

from ii_agent_tools.client import IIToolClient

from ii_agent.chat.types import ErrorTextContent, TextResultContent

from .base import BaseTool, ToolInfo, ToolCallInput, ToolResponse

MAX_RESULTS = 12


class ImageSearchTool(BaseTool):
    """Search for images using IIToolClient."""

    max_cost_usd = 0.05

    def __init__(self, tool_client: IIToolClient):
        self.tool_client = tool_client
        self._name = "image_search"

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="image_search",
            description=(
                "Searches for images on the web based on a query and returns URLs and metadata. "
                "Use this to find visual content, illustrations, diagrams, or reference images."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to find images",
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
            response = await self.tool_client.image_search(
                query=query,
                max_results=MAX_RESULTS,
            )
            results = response.result[:MAX_RESULTS]
            cost = response.cost or 0.0

            return ToolResponse(
                output=TextResultContent(value=json.dumps(results, indent=2)),
                cost_usd=cost,
            )

        except Exception as e:
            return ToolResponse(output=ErrorTextContent(value=f"Image search failed: {str(e)}"))
