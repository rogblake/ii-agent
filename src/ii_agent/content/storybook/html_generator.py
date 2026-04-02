"""HTML generator for storybook pages.

This module generates HTML content for storybook pages that can be:
1. Rendered directly in the frontend using an iframe or scoped styles
2. Rendered to PDF using Playwright for download functionality
"""

import logging
import re
from typing import Literal, Optional, Tuple

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

TextPosition = Literal["left", "right", "top", "bottom", "none", "separate_page"]

FLEX_DIRECTION_MAP: dict[str, str] = {
    "left": "row-reverse",
    "right": "row",
    "top": "column-reverse",
    "bottom": "column",
    "none": "row",
    "separate_page": "row",
}


def _parse_aspect_ratio(aspect_ratio: str) -> Tuple[int, int]:
    """Parse aspect ratio string to width and height components."""
    try:
        parts = aspect_ratio.split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        logger.warning(f"Invalid aspect_ratio '{aspect_ratio}', defaulting to 1:1")
        return 1, 1


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


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _get_flex_direction(text_position: TextPosition) -> str:
    """Map text position to CSS flex-direction."""
    return FLEX_DIRECTION_MAP.get(text_position, "row")


def generate_storybook_page_html(
    image_url: str,
    text_content: str,
    text_position: str,
    text_percentage: int,
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    page_number: int = 1,
) -> str:
    """Generate HTML for a storybook page.

    This generates a complete HTML document that can be:
    - Rendered in an iframe in the frontend
    - Converted to PDF using Playwright

    Args:
        image_url: URL to the AI-generated image
        text_content: Narrative text for the page
        text_position: Position of text (left/right/top/bottom/none/separate_page)
        text_percentage: Percentage of page for text (0-100, typically 20-30)
        aspect_ratio: Aspect ratio string (e.g., "1:1")
        resolution: Resolution (e.g., "1K", "2K", "4K")
        page_number: Page number (for accessibility)

    Returns:
        Complete HTML document string
    """
    # Calculate dimensions
    width, height = _calculate_dimensions(aspect_ratio, resolution)

    # Normalize text position
    text_pos: TextPosition = text_position if text_position in FLEX_DIRECTION_MAP else "none"

    # Check if we have text
    has_text = (
        text_pos != "none" and text_percentage > 0 and bool(text_content and text_content.strip())
    )

    if not has_text:
        return _generate_image_only_html(image_url, width, height, page_number)

    # Clamp text percentage to recommended range
    effective_text_percentage = text_percentage
    if not 20 <= text_percentage <= 30:
        logger.warning(
            f"text_percentage {text_percentage} outside recommended range 20-30, clamping"
        )
        effective_text_percentage = max(20, min(30, text_percentage))

    return _generate_composite_html(
        image_url=image_url,
        text_content=text_content,
        text_position=text_pos,
        text_percentage=effective_text_percentage,
        width=width,
        height=height,
        page_number=page_number,
    )


def _generate_image_only_html(
    image_url: str,
    width: int,
    height: int,
    page_number: int,
) -> str:
    """Generate HTML for an image-only page (no text)."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <meta name="page-number" content="{page_number}">
    <title>Storybook Page {page_number}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            margin: 0;
            width: {width}px;
            height: {height}px;
            overflow: hidden;
            background: #000000;
        }}

        .storybook-page {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #1a1a1a;
        }}

        .storybook-page img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
    </style>
</head>
<body>
    <div class="storybook-page" data-page="{page_number}">
        <img src="{image_url}" alt="Storybook page {page_number}" loading="eager" />
    </div>
</body>
</html>"""


def _generate_composite_html(
    image_url: str,
    text_content: str,
    text_position: TextPosition,
    text_percentage: int,
    width: int,
    height: int,
    page_number: int,
) -> str:
    """Generate HTML with image and text composite layout."""
    # Calculate image percentage (inverse of text percentage)
    image_percentage = 100 - text_percentage

    flex_direction = _get_flex_direction(text_position)
    escaped_text = _escape_html(text_content)
    base_font_size = max(18, int(min(width, height) * 0.028))

    # Determine if horizontal or vertical layout
    is_vertical = text_position in ("top", "bottom")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <meta name="page-number" content="{page_number}">
    <title>Storybook Page {page_number}</title>
    <style>
        @import url('https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400;1,600;1,700&display=swap');

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            margin: 0;
            width: {width}px;
            height: {height}px;
            overflow: hidden;
            background: #faf8f5;
        }}

        .storybook-page {{
            display: flex;
            flex-direction: {flex_direction};
            width: 100%;
            height: 100%;
        }}

        .image-section {{
            flex: 0 0 {image_percentage}%;
            overflow: hidden;
            background: #1a1a1a;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
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
            padding: {40 if is_vertical else 60}px;
            background: linear-gradient(135deg, #faf8f5 0%, #f5f2ed 100%);
            position: relative;
        }}

        .text-section::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4c8b8' fill-opacity='0.1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
            opacity: 0.5;
            pointer-events: none;
        }}

        .text-content {{
            font-family: 'Crimson Text', Georgia, 'Times New Roman', serif;
            font-size: {base_font_size}px;
            line-height: 1.9;
            color: #2c3e50;
            text-align: {"center" if is_vertical else "left"};
            max-width: 100%;
            max-height: 100%;
            overflow-y: auto;
            overflow-x: hidden;
            word-wrap: break-word;
            position: relative;
            z-index: 1;
            padding-right: 10px;
        }}

        .text-content::-webkit-scrollbar {{
            width: 8px;
        }}

        .text-content::-webkit-scrollbar-track {{
            background: rgba(212, 200, 184, 0.2);
            border-radius: 4px;
        }}

        .text-content::-webkit-scrollbar-thumb {{
            background: rgba(139, 69, 19, 0.3);
            border-radius: 4px;
        }}

        .text-content::-webkit-scrollbar-thumb:hover {{
            background: rgba(139, 69, 19, 0.5);
        }}
    </style>
</head>
<body>
    <div class="storybook-page" data-page="{page_number}">
        <div class="image-section">
            <img src="{image_url}" alt="Storybook page {page_number} illustration" loading="eager" />
        </div>
        <div class="text-section">
            <div class="text-content" data-editable="text">{escaped_text}</div>
        </div>
    </div>
</body>
</html>"""


def generate_text_only_page_html(
    text_content: str,
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    page_number: int = 1,
) -> str:
    """Generate HTML for a text-only page (no image).

    This is used for the "separate_page" text position mode where text
    is displayed on a dedicated page after the image page.

    Args:
        text_content: Narrative text for the page
        aspect_ratio: Aspect ratio string (e.g., "1:1")
        resolution: Resolution (e.g., "1K", "2K", "4K")
        page_number: Page number (for accessibility)

    Returns:
        Complete HTML document string
    """
    width, height = _calculate_dimensions(aspect_ratio, resolution)
    escaped_text = _escape_html(text_content)
    base_font_size = max(24, int(min(width, height) * 0.035))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={width}, height={height}">
    <meta name="page-number" content="{page_number}">
    <meta name="page-type" content="text-only">
    <title>Storybook Page {page_number}</title>
    <style>
        @import url('https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400;1,600;1,700&display=swap');

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            margin: 0;
            width: {width}px;
            height: {height}px;
            overflow: hidden;
            background: #faf8f5;
        }}

        .storybook-page {{
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #faf8f5 0%, #f5f2ed 100%);
            position: relative;
            padding: 80px;
        }}

        .storybook-page::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4c8b8' fill-opacity='0.1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
            opacity: 0.5;
            pointer-events: none;
        }}

        .text-content {{
            font-family: 'Crimson Text', Georgia, 'Times New Roman', serif;
            font-size: {base_font_size}px;
            line-height: 2.0;
            color: #2c3e50;
            text-align: center;
            max-width: 80%;
            max-height: 100%;
            overflow-y: auto;
            overflow-x: hidden;
            word-wrap: break-word;
            position: relative;
            z-index: 1;
        }}

        .text-content::-webkit-scrollbar {{
            width: 8px;
        }}

        .text-content::-webkit-scrollbar-track {{
            background: rgba(212, 200, 184, 0.2);
            border-radius: 4px;
        }}

        .text-content::-webkit-scrollbar-thumb {{
            background: rgba(139, 69, 19, 0.3);
            border-radius: 4px;
        }}

        .text-content::-webkit-scrollbar-thumb:hover {{
            background: rgba(139, 69, 19, 0.5);
        }}
    </style>
</head>
<body>
    <div class="storybook-page" data-page="{page_number}" data-type="text-only">
        <div class="text-content" data-editable="text">{escaped_text}</div>
    </div>
</body>
</html>"""


def generate_combined_page_html(
    image_url: str,
    text_content: str,
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    page_number: int = 1,
    text_is_html: bool = False,
) -> tuple[str, int, int]:
    """Generate HTML for a combined image + text page (for export).

    Layout: Image on LEFT (50%) + Text on RIGHT (50%)
    The combined page has double the width of the original aspect ratio.

    Args:
        image_url: URL to the AI-generated image
        text_content: Narrative text for the page (or raw HTML if text_is_html=True)
        aspect_ratio: Aspect ratio string (e.g., "1:1", "2:3")
        resolution: Resolution (e.g., "1K", "2K", "4K")
        page_number: Page number (for accessibility)
        text_is_html: If True, text_content is already HTML and won't be escaped

    Returns:
        Tuple of (html_content, combined_width, combined_height)
    """
    image_width, image_height = _calculate_dimensions(aspect_ratio, resolution)
    combined_width = image_width * 2
    combined_height = image_height

    escaped_text = text_content if text_is_html else _escape_html(text_content)
    base_font_size = max(24, int(min(image_width, image_height) * 0.035))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={combined_width}, height={combined_height}">
    <meta name="page-number" content="{page_number}">
    <meta name="page-type" content="combined">
    <title>Storybook Page {page_number}</title>
    <style>
        @import url('https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400;1,600;1,700&display=swap');

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            margin: 0;
            width: {combined_width}px;
            height: {combined_height}px;
            overflow: hidden;
            background: #faf8f5;
        }}

        .storybook-page {{
            display: flex;
            flex-direction: row;
            width: 100%;
            height: 100%;
        }}

        .image-section {{
            flex: 0 0 50%;
            width: {image_width}px;
            height: {image_height}px;
            overflow: hidden;
            background: #1a1a1a;
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
            flex: 0 0 50%;
            width: {image_width}px;
            height: {image_height}px;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 80px;
            background: linear-gradient(135deg, #faf8f5 0%, #f5f2ed 100%);
            position: relative;
        }}

        .text-section::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23d4c8b8' fill-opacity='0.1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
            opacity: 0.5;
            pointer-events: none;
        }}

        .text-content {{
            font-family: 'Crimson Text', Georgia, 'Times New Roman', serif;
            font-size: {base_font_size}px;
            line-height: 2.0;
            color: #2c3e50;
            text-align: center;
            max-width: 80%;
            max-height: 100%;
            overflow-y: auto;
            overflow-x: hidden;
            word-wrap: break-word;
            position: relative;
            z-index: 1;
        }}

        .text-content::-webkit-scrollbar {{
            width: 8px;
        }}

        .text-content::-webkit-scrollbar-track {{
            background: rgba(212, 200, 184, 0.2);
            border-radius: 4px;
        }}

        .text-content::-webkit-scrollbar-thumb {{
            background: rgba(139, 69, 19, 0.3);
            border-radius: 4px;
        }}

        .text-content::-webkit-scrollbar-thumb:hover {{
            background: rgba(139, 69, 19, 0.5);
        }}
    </style>
</head>
<body>
    <div class="storybook-page" data-page="{page_number}" data-type="combined">
        <div class="image-section">
            <img src="{image_url}" alt="Storybook page {page_number} illustration" loading="eager" />
        </div>
        <div class="text-section">
            <div class="text-content" data-editable="text">{escaped_text}</div>
        </div>
    </div>
</body>
</html>"""

    return (html, combined_width, combined_height)


def update_html_text_content(html_content: str, new_text: str) -> str:
    """Update the text content in an existing HTML document."""
    escaped_text = _escape_html(new_text)
    pattern = r'(<div class="text-content"[^>]*>)(.*?)(</div>)'
    replacement = rf"\1{escaped_text}\3"
    return re.sub(pattern, replacement, html_content, flags=re.DOTALL)


def update_html_image_url(html_content: str, new_image_url: str) -> str:
    """Update the image URL in an existing HTML document."""
    pattern = r'(<img[^>]*src=")[^"]*(")'
    replacement = rf"\1{new_image_url}\2"
    return re.sub(pattern, replacement, html_content)


def extract_image_url_from_html(html_content: str) -> Optional[str]:
    """Extract the image URL from an HTML document."""
    pattern = r'<img[^>]*src="([^"]*)"'
    match = re.search(pattern, html_content)
    if match:
        return match.group(1)
    return None


def extract_text_content_from_html(html_content: str) -> Optional[str]:
    """Extract the text content (inner HTML) from the .text-content div."""
    pattern = r'<div class="text-content"[^>]*>(.*?)</div>'
    match = re.search(pattern, html_content, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def combine_html_pages_for_export(
    image_page_html: str,
    text_page_html: str,
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    page_number: int = 1,
) -> tuple[str, int, int]:
    """Combine image and text HTML pages into a single page for export.

    Takes the stored HTML from both pages and combines them side-by-side,
    preserving all original styling. Image page on the left, text page on the right.

    Args:
        image_page_html: Complete HTML content of the image page
        text_page_html: Complete HTML content of the text page
        aspect_ratio: Aspect ratio string (e.g., "1:1", "2:3")
        resolution: Resolution (e.g., "1K", "2K", "4K")
        page_number: Page number (for accessibility)

    Returns:
        Tuple of (combined_html, combined_width, combined_height)
    """
    image_width, image_height = _calculate_dimensions(aspect_ratio, resolution)
    combined_width = image_width * 2
    combined_height = image_height

    def extract_styles(html: str) -> str:
        pattern = r"<style[^>]*>(.*?)</style>"
        matches = re.findall(pattern, html, flags=re.DOTALL)
        return "\n".join(matches)

    def extract_body_content(html: str) -> str:
        pattern = r"<body[^>]*>(.*?)</body>"
        match = re.search(pattern, html, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def prefix_css_selectors(css: str, prefix: str) -> str:
        css = re.sub(r"@import[^;]+;", "", css)
        result = []
        rules = re.split(r"(\})", css)
        current_rule = ""
        for part in rules:
            current_rule += part
            if part == "}":
                match = re.match(r"\s*([^{]+)\{([^}]*)\}", current_rule, re.DOTALL)
                if match:
                    selector = match.group(1).strip()
                    body = match.group(2)
                    if selector in ["html", "body", "html, body", "*"]:
                        current_rule = ""
                        continue
                    selectors = [s.strip() for s in selector.split(",")]
                    prefixed_selectors = [f".{prefix} {s}" for s in selectors if s]
                    if prefixed_selectors:
                        result.append(f"{', '.join(prefixed_selectors)} {{{body}}}")
                current_rule = ""
        return "\n".join(result)

    image_styles = extract_styles(image_page_html)
    text_styles = extract_styles(text_page_html)
    image_body = extract_body_content(image_page_html)
    text_body = extract_body_content(text_page_html)

    scoped_image_styles = prefix_css_selectors(image_styles, "combined-left")
    scoped_text_styles = prefix_css_selectors(text_styles, "combined-right")

    combined_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width={combined_width}, height={combined_height}">
    <meta name="page-number" content="{page_number}">
    <meta name="page-type" content="combined">
    <title>Storybook Page {page_number}</title>
    <style>
        @import url('https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css');
        @import url('https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400;1,600;1,700&display=swap');

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        html, body {{
            margin: 0;
            width: {combined_width}px;
            height: {combined_height}px;
            overflow: hidden;
            background: #000;
        }}

        .combined-container {{
            display: flex;
            flex-direction: row;
            width: 100%;
            height: 100%;
        }}

        .combined-left,
        .combined-right {{
            flex: 0 0 50%;
            width: {image_width}px;
            height: {image_height}px;
            overflow: hidden;
            position: relative;
        }}

        /* Ensure storybook-page fills its container */
        .combined-left .storybook-page,
        .combined-right .storybook-page {{
            width: 100% !important;
            height: 100% !important;
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
        }}
    </style>
    <style>
        /* Image page styles (scoped) */
        {scoped_image_styles}
    </style>
    <style>
        /* Text page styles (scoped) */
        {scoped_text_styles}
    </style>
</head>
<body>
    <div class="combined-container" data-page="{page_number}" data-type="combined">
        <div class="combined-left">
            {image_body}
        </div>
        <div class="combined-right">
            {text_body}
        </div>
    </div>
</body>
</html>"""

    return (combined_html, combined_width, combined_height)
