"""Composite image service for rendering HTML layouts to PNG images via tool server."""

import base64
import logging
import os
import uuid
from typing import Literal, Tuple

import httpx

logger = logging.getLogger(__name__)

# Resolution to pixel mapping
RESOLUTION_PIXELS: dict[str, int] = {
    "1K": 1024,
    "2K": 2048,
    "4K": 4096,
}
DEFAULT_PIXELS = 1024

# Default dimensions
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080

TextPosition = Literal["left", "right", "top", "bottom", "none"]


def _parse_aspect_ratio(aspect_ratio: str) -> Tuple[int, int]:
    """Parse aspect ratio string to width and height components."""
    try:
        parts = aspect_ratio.split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        logger.warning(f"Invalid aspect_ratio '{aspect_ratio}', defaulting to 16:9")
        return 16, 9


def _round_to_even(value: int) -> int:
    """Round to even number for video codec compatibility."""
    return value if value % 2 == 0 else value + 1


def _calculate_dimensions(aspect_ratio: str, resolution: str) -> Tuple[int, int]:
    """Calculate width and height from aspect ratio and resolution."""
    ratio_w, ratio_h = _parse_aspect_ratio(aspect_ratio)
    base_pixels = RESOLUTION_PIXELS.get(resolution, DEFAULT_PIXELS)

    # The base_pixels represents the shorter dimension
    if ratio_w >= ratio_h:
        height = base_pixels
        width = int((base_pixels * ratio_w) / ratio_h)
    else:
        width = base_pixels
        height = int((base_pixels * ratio_h) / ratio_w)

    return _round_to_even(width), _round_to_even(height)


async def create_composite(
    image_url: str,
    text_content: str,
    text_position: TextPosition,
    text_percentage: int,
    session_id: uuid.UUID | str = "default",
    user_api_key: str | None = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1K",
) -> bytes:
    """
    Create a composite image combining an AI-generated image with text.

    This service calls the tool server's /composite-image endpoint for HTML rendering,
    avoiding the need to install Playwright in the agent.
    """
    has_text = text_position != "none" and bool(text_content.strip())

    effective_text_percentage = 0
    if has_text:
        if not 20 <= text_percentage <= 30:
            logger.warning(f"text_percentage {text_percentage} outside recommended range 20-30, clamping")
            effective_text_percentage = max(20, min(30, text_percentage))
        else:
            effective_text_percentage = text_percentage

    width, height = _calculate_dimensions(aspect_ratio, resolution)

    html_content = _generate_html(
        image_url=image_url,
        text_content=text_content,
        text_position=text_position,
        text_percentage=effective_text_percentage,
        width=width,
        height=height,
    )

    return await _render_via_tool_server(html_content, session_id, user_api_key, width, height)


async def _render_via_tool_server(
    html_content: str,
    session_id: uuid.UUID | str = "default",
    user_api_key: str | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> bytes:
    """Call tool server's /composite-image endpoint to render HTML to PNG."""
    tool_server_url = os.getenv("TOOL_SERVER_URL")
    if not tool_server_url:
        raise RuntimeError("TOOL_SERVER_URL is not configured")

    if not user_api_key:
        raise RuntimeError("user_api_key is required for tool server authentication")

    logger.info(f"[COMPOSITE] Calling tool server for HTML->PNG rendering ({width}x{height})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{tool_server_url}/composite-image",
                json={
                    "session_id": str(session_id),
                    "html_content": html_content,
                    "width": width,
                    "height": height,
                },
                headers={"Authorization": f"Bearer {user_api_key}"},
                timeout=60.0,
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("success"):
                raise RuntimeError(f"Tool server rendering failed: {result.get('error', 'Unknown error')}")

            image_base64 = result.get("image_base64")
            if not image_base64:
                raise RuntimeError("No image data returned from tool server")

            png_bytes = base64.b64decode(image_base64)
            logger.info(f"[COMPOSITE] Successfully rendered PNG via tool server ({len(png_bytes)} bytes)")
            return png_bytes

    except httpx.HTTPError as e:
        logger.error(f"[COMPOSITE] HTTP error calling tool server: {e}")
        raise RuntimeError(f"Failed to call tool server: {e}") from e
    except Exception as e:
        logger.error(f"[COMPOSITE] Error rendering via tool server: {e}", exc_info=True)
        raise


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _generate_html(
    image_url: str,
    text_content: str,
    text_position: TextPosition,
    text_percentage: int,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> str:
    """Generate HTML with flexbox layout for image + text composition."""
    has_text = text_position != "none" and text_percentage > 0 and bool(text_content.strip())

    if not has_text:
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            width: {width}px;
            height: {height}px;
            overflow: hidden;
            background: #ffffff;
        }}

        .image-only {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f0f0f0;
        }}

        .image-only img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
    </style>
</head>
<body>
    <div class="image-only">
        <img src="{image_url}" alt="Story scene" />
    </div>
</body>
</html>"""

    # Calculate image percentage (inverse of text percentage)
    image_percentage = 100 - text_percentage

    flex_direction = _get_flex_direction(text_position)
    escaped_text = _escape_html(text_content)
    base_font_size = max(16, int(min(width, height) * 0.025))

    # Generate HTML template
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            width: {width}px;
            height: {height}px;
            overflow: hidden;
            background: #ffffff;
        }}

        .container {{
            display: flex;
            flex-direction: {flex_direction};
            width: 100%;
            height: 100%;
        }}

        .image-section {{
            flex: 0 0 {image_percentage}%;
            overflow: hidden;
            background: #f0f0f0;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .image-section img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}

        .text-section {{
            flex: 0 0 {text_percentage}%;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 60px;
            background: #ffffff;
        }}

        .text-content {{
            font-family: Georgia, 'Times New Roman', serif;
            font-size: {base_font_size}px;
            line-height: 1.8;
            color: #2c3e50;
            text-align: left;
            max-width: 100%;
            word-wrap: break-word;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="image-section">
            <img src="{image_url}" alt="Story scene" />
        </div>
        <div class="text-section">
            <div class="text-content">{escaped_text}</div>
        </div>
    </div>
</body>
</html>"""

    return html


FLEX_DIRECTION_MAP: dict[str, str] = {
    "left": "row-reverse",
    "right": "row",
    "top": "column-reverse",
    "bottom": "column",
    "none": "row",
}


def _get_flex_direction(text_position: TextPosition) -> str:
    """Map text position to CSS flex-direction."""
    return FLEX_DIRECTION_MAP.get(text_position, "row")
