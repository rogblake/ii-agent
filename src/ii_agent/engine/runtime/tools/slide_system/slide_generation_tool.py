from typing import Any, List, TYPE_CHECKING
import asyncio
import httpx
from ii_agent.engine.runtime.tools.slide_system.hook_utils import (
    persist_slide_tool_result,
    process_slide_content,
)
from ii_agent.engine.runtime.tools.base import ToolResult
from ii_agent.engine.runtime.tools.slide_system.base import SlideToolBase

if TYPE_CHECKING:
    from ii_agent.engine.runtime.agents.agent import IIAgent
    from ii_agent.engine.runtime.tools.function import FunctionCall

NAME = "SlideGenerate"
DISPLAY_NAME = "Generate Slide Image"
DESCRIPTION = """Generates a presentation slide as a high-quality image using AI.

This tool creates visually stunning slide images in 16:9 aspect ratio (1920x1080).
Use this tool when you want to create professional, design-quality slides without writing HTML/CSS.

KEY FEATURES:
- Generates complete slide images with professional design
- Creates slides with proper typography, layout, and visual hierarchy
- Automatically uploads to cloud storage and returns the image URL
- Perfect for presentations that need high-quality visuals
- **STYLE CONSISTENCY**: Pass reference_image_url to maintain visual consistency across slides

WHEN TO USE:
- Creating visually impressive title/cover slides
- Generating infographic-style content slides
- Creating slides with complex visual layouts
- When you need design-quality slides without HTML expertise
- For presentations where visual impact is crucial

STYLE CONSISTENCY (CRITICAL for multi-slide presentations):
- To maintain consistent visual style across slides, pass reference_image_url with the URL of a previously generated slide
- When reference_image_url is provided, the new slide will match the reference's: background color, accent color, font style, chart/icon style
- If no reference_image_url is provided, a new style will be generated based on the prompt

PROMPT TIPS:
1. Be specific about the content you want on the slide
2. Mention any specific colors, themes, or styles you prefer
3. Describe the visual elements you want (icons, images, charts)
4. Specify the mood/tone (professional, playful, modern, classic)
5. Include the slide type in your prompt (cover, content, chart, etc.)

Examples:
- "Create a cover slide for 'AI in Healthcare' presentation with a futuristic blue theme and medical imagery. Title: 'Artificial Intelligence in Healthcare'. Subtitle: 'Transforming Patient Care'"
- "Create a content slide showing 3 key benefits of cloud computing with icons and brief descriptions. Use a clean, corporate design with blue accents."
- "Create a chart slide visualizing quarterly sales growth from Q1 to Q4 2024 with a clean, professional design. Show an upward trend."
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "presentation_name": {
            "type": "string",
            "description": "Name of the presentation (used for organizing slides)",
        },
        "slide_number": {
            "type": "integer",
            "description": "Slide number (1-based)",
            "minimum": 1,
        },
        "prompt": {
            "type": "string",
            "description": "Complete prompt describing the slide to generate. Include slide type, title, content, style, and any visual elements.",
        },
        "title": {
            "type": "string",
            "description": "Title of the slide (for metadata)",
        },
        "description": {
            "type": "string",
            "description": "Brief description of the slide purpose (for metadata)",
        },
        "reference_image_url": {
            "type": "string",
            "description": "URL of a previously generated slide to use as style reference. When provided, the new slide will maintain visual consistency with the reference (same background color, accent color, font style, chart/icon style).",
        },
    },
    "required": [
        "presentation_name",
        "slide_number",
        "prompt",
        "title",
        "description",
    ],
}
DEFAULT_TIMEOUT = 120
SLIDE_SYSTEM_INSTRUCTION = """
Use this tool if no template info is provided. If there's template involved, default to create slide tool

You are a world-class presentation designer and visual storyteller.
Your task is to create a single, visually stunning presentation slide as an image.

CRITICAL REQUIREMENTS:
1. Generate EXACTLY ONE slide image in 16:9 aspect ratio (landscape orientation)
2. The slide must be self-contained and visually complete
3. Use professional design principles: clear hierarchy, balanced composition, readable text
4. Incorporate modern design trends: clean layouts, strategic use of white space
5. Text should be large and readable - minimum 24pt equivalent for body, 48pt+ for titles
6. Use high contrast for text readability
7. Include visual elements that support the content (icons, shapes, images where appropriate)
8. Maintain consistent visual style appropriate for business/educational presentations

DESIGN GUIDELINES:
- Title slides: Bold, centered title with subtitle, clean background
- Content slides: Clear title, organized bullet points or sections, supporting visuals
- Data slides: Clean charts/graphs with clear labels and legends
- Image-heavy slides: High-quality imagery with minimal overlaid text
- Conclusion slides: Memorable key takeaways, call-to-action if relevant

COLOR AND STYLE:
- Use professional color palettes that work for presentations
- Ensure sufficient contrast between text and background
- Apply consistent styling throughout
"""
STYLE_REFERENCE_INSTRUCTION = (
    "STYLE REFERENCE: The above image(s) show the established visual style. "
    "STRICTLY MAINTAIN: same background color, same accent color, same font style, "
    "same chart/icon style. Keep visual consistency with these reference slides."
)


class SlideGenerationTool(SlideToolBase):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
    requires_confirmation = False

    def __init__(self) -> None:
        super().__init__()
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
            tool_name=self.name,
            tool_input=fc.arguments or {},
            user_display_content=processed_display,
        )

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Execute the slide generation operation via tool server."""
        presentation_name = tool_input.get("presentation_name")
        slide_number = tool_input.get("slide_number")
        prompt = tool_input.get("prompt")
        title = tool_input.get("title")
        description = tool_input.get("description")
        reference_image_url = tool_input.get("reference_image_url")

        if not presentation_name or not slide_number or not title or not description or not prompt:
            return ToolResult(
                llm_content="Presentation name, slide number, title, and description are required",
                user_display_content="Presentation name, slide number, title, and description are required",
                is_error=True,
            )

        try:
            # Get presentation path for metadata
            presentation_path = self._get_presentation_path(presentation_name)

            # Create presentation directory if it doesn't exist in sandbox
            await self.sandbox.run_command(f"mkdir -p {presentation_path}")
            # Load or create metadata
            metadata = await self._load_metadata(presentation_path)

            # Update presentation name in metadata if empty
            if not metadata["presentation"]["name"]:
                metadata["presentation"]["name"] = presentation_name
                metadata["presentation"]["title"] = presentation_name

            # Build reference image URLs list for style consistency
            reference_image_urls: List[str] = []
            if reference_image_url:
                # Use explicitly provided reference URL
                reference_image_urls.append(reference_image_url)
            elif slide_number > 2:
                # Auto-detect: try to get slide 2's image URL from metadata for consistency
                slide_2_entry = self._find_slide_in_metadata(metadata, 2)
                if slide_2_entry and slide_2_entry.get("image_url"):
                    reference_image_urls.append(slide_2_entry["image_url"])

            full_prompt = self._build_slide_prompt(prompt, reference_image_urls)

            max_retries = 5
            retry_delay_seconds = 5
            last_exc: Exception | None = None

            for attempt in range(1, max_retries + 1):
                try:
                    result = await self.dependencies.tool_client.generate_image(
                        prompt=full_prompt,
                        aspect_ratio="16:9",
                        image_size="1K",
                        image_urls=reference_image_urls,
                        model_name="gemini-3-pro-image-preview",
                        provider="vertex",
                    )
                    last_exc = None
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries:
                        await asyncio.sleep(retry_delay_seconds)
                    else:
                        raise

            if last_exc is not None:
                raise last_exc

            # Extract result data
            image_url = result.url
            storage_path = result.storage_path
            image_size = result.size
            mime_type = result.mime_type

            if not image_url:
                return ToolResult(
                    llm_content="ERROR: Slide generation did not return a valid image URL",
                    is_error=True,
                )

            # Update metadata with the generated slide info
            metadata = self._update_slide_in_metadata(
                metadata=metadata,
                slide_number=slide_number,
                title=title,
                description=description,
                slide_type="image",
            )

            # Add image-specific metadata
            slide_entry = self._find_slide_in_metadata(metadata, slide_number)
            if slide_entry:
                slide_entry["is_image_slide"] = True
                slide_entry["image_url"] = image_url
                slide_entry["image_storage_path"] = storage_path
                slide_entry["image_mime_type"] = mime_type
                slide_entry["image_size"] = image_size

            # Save metadata
            await self._save_metadata(presentation_path, metadata)

            total_slides = len(metadata.get("slides", []))

            # Build the content to return - HTML wrapper for the image
            image_html = self._create_image_slide_html(
                image_url=image_url,
                title=title,
                slide_number=slide_number,
            )

            # Save the HTML file in sandbox
            slide_filename = self._get_slide_filename(slide_number)
            slide_filepath = f"{presentation_path}/{slide_filename}"
            await self.sandbox.write_file(slide_filepath, image_html)

            # Build workspace filepath
            workspace_filepath = f"/workspace/{presentation_path}/slide_{slide_number:03d}.html"

            tool_result = ToolResult(
                llm_content=(
                    f"Successfully generated slide {slide_number} image for '{presentation_name}'\n"
                    f"Title: {title}\n"
                    f"Image URL: {image_url}\n"
                    f"Size: {image_size} bytes\n"
                    f"Total slides in presentation: {total_slides}"
                ),
                user_display_content={
                    "content": image_html,
                    "filepath": workspace_filepath,
                    "image_url": image_url,
                    "is_image_slide": True,
                },
                is_error=False,
                cost=result.cost,
            )

            return tool_result

        except httpx.HTTPStatusError as e:
            return ToolResult(
                llm_content=f"ERROR: Tool server returned error: {e.response.status_code} - {e.response.text}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"ERROR: Failed to generate slide: {str(e)}", is_error=True
            )

    def _build_slide_prompt(self, prompt: str, reference_image_urls: List[str]) -> str:
        prompt_parts = [SLIDE_SYSTEM_INSTRUCTION.strip()]
        if reference_image_urls:
            prompt_parts.append(STYLE_REFERENCE_INSTRUCTION)
        prompt_parts.append(prompt)
        return "\n\n".join(prompt_parts)

    def _create_image_slide_html(self, image_url: str, title: str, slide_number: int) -> str:
        """
        Create an HTML wrapper for the image slide.

        This HTML will be stored in the database and rendered by the frontend.
        The frontend will detect this is an image slide and render it appropriately.
        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="slide-type" content="image">
    <meta name="slide-number" content="{slide_number}">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            width: 1280px;
            height: 720px;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #000;
        }}
        .slide-image {{
            width: 100%;
            height: 100%;
            object-fit: contain;
        }}
    </style>
</head>
<body data-is-image-slide="true" data-image-url="{image_url}">
    <img src="{image_url}" alt="{title}" class="slide-image" />
</body>
</html>"""
