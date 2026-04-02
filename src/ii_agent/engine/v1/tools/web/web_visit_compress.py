from typing import Any, Dict

from ii_agent.engine.v1.tools.base import BaseAgentTool, ToolResult


# Name
NAME = "web_visit_compress"
DISPLAY_NAME = "Web Visit Compress"

# Tool description
DESCRIPTION = "You should call this tool when you need to visit a webpage and extract relevant content. Returns relevant webpage content as text."

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "urls": {
            "type": "array",
            "items": {
                "type": "string",
            },
            "description": "The urls of the webpages to visit.",
        },
        "query": {
            "type": "string",
            "description": "The query to extract relevant content.",
        },
    },
    "required": ["urls", "query"],
}


class WebVisitCompressTool(BaseAgentTool):
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
        urls = tool_input["urls"]
        query = tool_input["query"]
        process_urls = []
        for url in urls:
            if "arxiv.org/abs" in url:
                url = "https://arxiv.org/html/" + url.split("/")[-1]
            process_urls.append(url)

        try:
            response = await self.dependencies.tool_client.researcher_web_visit(process_urls, query)
            content = response.content
        except Exception as exc:
            return ToolResult(
                llm_content="",
                user_display_content=str(exc),
                is_error=True,
            )

        return ToolResult(
            llm_content=content,
            user_display_content=content,
            cost=response.cost,
        )
