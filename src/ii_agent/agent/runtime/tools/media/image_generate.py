from ii_agent.agent.runtime.tools.sandbox.base import BaseSandboxTool
import httpx

from typing import Any, TYPE_CHECKING

from ii_agent.agent.runtime.tools.base import ToolResult, FileURLContent
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agents.agent import IIAgent
    from ii_agent.agent.runtime.tools.function import FunctionCall

# Name
NAME = "generate_image"
DISPLAY_NAME = "Generate Image"

# Tool description
DESCRIPTION = """Generates high-quality image from text prompt. The generated image will be saved as a PNG file to your specified workspace location

Use this tool to create custom images for web applications, presentations, or documentation:
- Creating hero images with emotional resonance and clear focal points for landing pages
- Generating product images with clean backgrounds and professional lighting
- Generating high-impact visuals for marketing materials and presentations
- Creating custom icons, logos, or UI elements with consistent style

For best results, structure your prompts with these elements:
1. Subject Description: Clearly define the main focus (person, object, scene, concept). Example:
- "A modern smartphone", "Professional businesswoman", "Mountain landscape"
2. Visual Style & Medium: Specify the artistic approach and rendering style. Example:
- Photography styles: "Professional headshot", "Product photography with studio lighting"
- Digital art: "Digital illustration", "3D render", "Minimalist vector art"
- Traditional art: "Oil painting", "Watercolor", "Pencil sketch", "Cartoon style"
3. Composition & Setting: Describe the environment, background, and spatial arrangement. Example:
- "Clean white background", "Modern office environment", "Sunset over ocean"
- "Close-up view", "Wide angle shot", "Bird's eye perspective"
4. Lighting & Mood: Enhance atmosphere and visual appeal. Example:
- "Soft natural lighting", "Dramatic shadows", "Warm golden hour light"
- "Professional studio lighting", "Cinematic lighting", "Bright and airy"
5. Technical Specifications: Add quality and detail modifiers. Example:
- "High resolution", "Sharp focus", "Detailed textures", "Professional quality"
- "Clean composition", "Balanced colors", "High contrast"

Supported Aspect Ratios:
- 1:1 (Square) - Perfect for social media posts, avatars, icons
- 16:9 (Landscape) - Ideal for banners, headers, presentation slides  
- 9:16 (Portrait) - Great for mobile screens, stories, vertical banners
- 4:3 (Standard) - Classic format for general content, presentations
- 3:4 (Portrait) - Suitable for posters, flyers, portrait-oriented content"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "A detailed description of the image to be generated",
        },
        "output_path": {
            "type": "string",
            "description": "The absolute path for the output PNG image file within the workspace (e.g., '/workspace/generated_images/my_image.png'). Must end with .png",
        },
        "aspect_ratio": {
            "type": "string",
            "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
            "default": "1:1",
            "description": "The aspect ratio for the generated image",
        },
    },
    "required": ["prompt", "output_path"],
}

DEFAULT_TIMEOUT = 120
DEFAULT_IMAGE_GENERATION_MAX_COST_USD = 0.05


class ImageGenerateTool(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True
    max_cost_usd = DEFAULT_IMAGE_GENERATION_MAX_COST_USD

    def __init__(
        self,
    ):
        super().__init__()

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if not agent.sandbox:
            raise ValueError(f"Tool {self.name} requires running sandbox before execution!")
        self.sandbox = agent.sandbox
        self.session_id = agent.session_id
        return

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        output_path = tool_input["output_path"]
        if not output_path.lower().endswith(".png"):
            return ToolResult(llm_content="Error: output_path must end with .png", is_error=True)

        # output_path = Path(output_path).resolve() # TODO : change to bash using
        # output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = await self.dependencies.tool_client.generate_image(
                prompt=tool_input["prompt"],
                aspect_ratio=tool_input.get("aspect_ratio", "1:1"),
                background=tool_input.get("background", "auto"),
                metadata={
                    "session_id": self.session_id,
                },
            )
        except Exception as exc:
            return ToolResult(
                llm_content=f"Image generation failed: {exc}",
                is_error=True,
            )

        image_url = response.url
        image_mime_type = response.mime_type or "image/png"
        image_size = response.size or 0
        search_results = response.search_results or []

        if not image_url:
            if search_results:
                summary_path = await self._write_search_summary(
                    output_path=output_path,
                    prompt=tool_input["prompt"],
                    search_results=search_results,
                )
                return ToolResult(
                    llm_content=(
                        "Image generation was unavailable. "
                        f"DuckDuckGo image search results were saved to {summary_path}."
                    ),
                )
            return ToolResult(
                llm_content="Error: Image generation did not return a valid image URL",
                is_error=True,
            )

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as download_client:
                download_response = await download_client.get(image_url)
                download_response.raise_for_status()

        except httpx.HTTPError as exc:
            return ToolResult(
                llm_content=f"Error downloading image: {exc}",
                is_error=True,
            )
        try:
            await self.sandbox.write_file(output_path, download_response.content)
        except httpx.HTTPError as exc:
            return ToolResult(
                llm_content=f"Error downloading image: {exc}",
                is_error=True,
            )

        return ToolResult(
            llm_content=f"![Generated Image]({image_url})",
            user_display_content=FileURLContent(
                type="file_url",
                url=image_url,
                mime_type=image_mime_type,
                name=output_path,
                size=image_size,
            ).model_dump(),
            cost=response.cost,
        )

    async def _write_search_summary(
        self,
        output_path: str,
        prompt: str,
        search_results: list[dict[str, Any]],
    ) -> str:
        summary_path = ".".join(output_path.split(".")[:-1]) + ".md"
        lines = [
            "# DuckDuckGo image search results",
            f"Prompt: {prompt}",
            "",
        ]
        for idx, result in enumerate(search_results, start=1):
            title = result.get("title") or "Untitled image"
            source = result.get("source") or "Unknown source"
            image_url = result.get("image_url") or result.get("url") or ""
            lines.append(f"{idx}. **{title}**")
            lines.append(f"   Source: {source}")
            if image_url:
                lines.append(f"   URL: {image_url}")
            lines.append("")

        # summary_path.parent.mkdir(parents=True, exist_ok=True)
        await self.sandbox.write_file(summary_path, "\n".join(lines))
        return summary_path
