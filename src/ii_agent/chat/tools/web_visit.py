"""Web visit tool - delegates to IIToolClient."""

import json

from ii_agent_tools.client import IIToolClient

from ii_agent.chat.types import ErrorTextContent, TextResultContent

from .base import BaseTool, ToolInfo, ToolCallInput, ToolResponse


class WebVisitTool(BaseTool):
    """Visit a URL and extract its content using IIToolClient."""

    max_cost_usd = 0.05

    def __init__(self, tool_client: IIToolClient):
        self.tool_client = tool_client
        self._name = "web_visit"

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="web_visit",
            description=(
                "Visits a URL and extracts its content. Use this to read documentation, "
                "articles, or any web page content. Combine with web_search to first find "
                "relevant URLs, then visit them for full content."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to visit and extract content from",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Optional prompt to guide what information to extract from the page",
                    },
                },
            },
            required=["url"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        try:
            params = json.loads(tool_call.input)
            url = params["url"]
            prompt = params.get("prompt")
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {e}"))

        try:
            response = await self.tool_client.web_visit(url, prompt)
            content = response.content
            cost = response.cost or 0.0

            if content is None or (isinstance(content, str) and not content.strip()):
                return ToolResponse(
                    output=TextResultContent(value="No content extracted."),
                    cost_usd=cost,
                )

            return ToolResponse(
                output=TextResultContent(value=content),
                cost_usd=cost,
            )

        except Exception as e:
            return ToolResponse(
                output=ErrorTextContent(value=f"Failed to visit {url}: {str(e)}"),
            )
