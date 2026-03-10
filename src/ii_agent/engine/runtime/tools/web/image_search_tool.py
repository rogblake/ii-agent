import json
from typing import Any

from ii_agent.engine.runtime.tools.base import BaseAgentTool, ToolResult


# Name
NAME = "image_search"
DISPLAY_NAME = "Image Search"

# Tool description
DESCRIPTION = """Searches the web for images based on your query and returns relevant results with metadata.

Usage:
- Use this tool for factual or real-world image needs for your project, website, presentation, etc.
- Get high-quality images by setting the minimum width and height with higher values
- Use the aspect ratio and image type filters to find images that match your project's design requirements
- For non-factual scenarios, artistic or creative image needs, use `generate_image` tool instead

Don't worry about the license or copyright issues. This tool is designed to find images that are free to use and are not copyrighted.
Use `read_remote_image` to check the quality and content of returned images before incorporating them into your project."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search terms to find images. Use descriptive keywords for best results (e.g., 'modern office interior', 'abstract geometric pattern', 'fresh vegetables on white background')",
        },
        "aspect_ratio": {
            "type": "string",
            "enum": ["all", "square", "tall", "wide", "panoramic"],
            "default": "all",
            "description": "Filter images by aspect ratio. Options: 'all' (any ratio), 'square' (1:1, ideal for social media posts), 'tall' (portrait orientation), 'wide' (16:9 or similar, perfect for banners), 'panoramic' (ultra-wide for headers). Default is 'all'.",
        },
        "image_type": {
            "type": "string",
            "enum": ["all", "face", "photo", "clipart", "lineart", "animated"],
            "default": "all",
            "description": "Filter by image type. Options: 'all' (any type), 'face' (portraits and people), 'photo' (realistic photographs), 'clipart' (graphics and illustrations), 'lineart' (drawings and sketches), 'animated' (GIFs and animations). Default is 'all'.",
        },
        "min_width": {
            "type": "number",
            "default": 300,
            "description": "Minimum image width in pixels. Use this to ensure images meet resolution requirements (e.g., 1920 for HD displays, 300 for thumbnails). Default is 300.",
        },
        "min_height": {
            "type": "number",
            "default": 300,
            "description": "Minimum image height in pixels. Use this to ensure images meet resolution requirements (e.g., 1080 for HD displays, 300 for thumbnails). Default is 300.",
        },
        "is_product": {
            "type": "boolean",
            "default": False,
            "description": "Set to true to prioritize product images from shopping and e-commerce sites. Useful for finding commercial product photos, catalog images, and shopping-related visuals. Default is false.",
        },
    },
    "required": ["query"],
}

MAX_RESULTS = 5


class ImageSearchTool(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self):
        super().__init__()

    def _format_results(self, results: list[dict[str, Any]]) -> str:
        """The results is the list of dicts with the following keys:
        {
            "title": str,
            "source": str,
            "image_url": str,
            "width": int,
            "height": int,
            "is_product": bool,
        }
        """

        llm_content = ""
        for result in results:
            llm_content += f"Title: {result.get('title', '')}\n"
            llm_content += f"Source: {result.get('source', '')}\n"
            llm_content += f"Image URL: {result.get('image_url', '')}\n"
            llm_content += f"Width: {result.get('width', 0)}\n"
            llm_content += f"Height: {result.get('height', 0)}\n"
            llm_content += "--------------------------------\n"

        return llm_content

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        query = tool_input["query"]
        aspect_ratio = tool_input.get("aspect_ratio", "all")
        image_type = tool_input.get("image_type", "all")
        min_width = tool_input.get("min_width", 0)
        min_height = tool_input.get("min_height", 0)
        is_product = tool_input.get("is_product", False)

        try:
            response = await self.dependencies.tool_client.image_search(
                query=query,
                aspect_ratio=aspect_ratio,
                image_type=image_type,
                min_width=min_width,
                min_height=min_height,
                is_product=is_product,
                max_results=MAX_RESULTS,
            )
            results = response.result[:MAX_RESULTS]
        except Exception as exc:
            return ToolResult(
                llm_content=f"The search request failed: {exc}.",
                is_error=True,
            )

        if len(results) == 0:
            return ToolResult(
                llm_content="No results found. Please try again with different keywords, broader terms or try updating the parameters",
                is_error=False,
            )

        llm_content = self._format_results(results)

        # TODO: custom the user display content
        return ToolResult(
            llm_content=llm_content,
            user_display_content=json.dumps(results, indent=2),
            cost=response.cost,
        )
