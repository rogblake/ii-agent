"""Business logic for Nano Banana design mode.

Handles:
- Vision-based component detection via LLMExecutionService (provider-agnostic)
- HTML overlay generation for interactive editing
- Image regeneration with modifications
- Version tracking and management
"""

from __future__ import annotations

import logging
import re
from html import escape as html_escape
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import BinaryContent, MessageRole, TextContent, ToolCall
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.llm.execution_service import LLMExecutionService
from ii_agent.projects.design.utils.constants import (
    DESIGN_MODE_GOOGLE_FONTS,
    DESIGN_MODE_RUNTIME_SCRIPT,
)

from .prompts import (
    COMPONENT_DETECTION_PROMPT,
    REMOVE_BACKGROUND_PROMPT,
    build_regeneration_prompt,
)
from .repository import NanoBananaRepository, extract_image_url_from_slide_html
from .schemas import (
    BoundingBox,
    ComponentStyles,
    DetectRequest,
    DetectResponse,
    DetectedComponent,
    GetVersionsResponse,
    Instruction,
    RegenerateRequest,
    RegenerateResponse,
    RemoveBackgroundRequest,
    RemoveBackgroundResponse,
    RevertRequest,
    RevertResponse,
    SlideVersionInfo,
)

logger = logging.getLogger(__name__)

# Text component types that may have editable text
TEXT_COMPONENT_TYPES = frozenset(
    [
        "title",
        "subtitle",
        "text_block",
        "bullet_list",
        "footer",
        "header",
        "text",
    ]
)

# Tool name used for structured detection output
_DETECT_TOOL_NAME = "submit_detected_components"

# OpenAI-format tool definition for component detection
DETECT_COMPONENTS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": _DETECT_TOOL_NAME,
        "description": (
            "Submit the detected visual components found in the slide image. "
            "Call this tool exactly once with all detected components."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "components": {
                    "type": "array",
                    "description": "List of all detected visual components",
                    "items": {
                        "type": "object",
                        "properties": {
                            "component_type": {
                                "type": "string",
                                "enum": [
                                    "title",
                                    "subtitle",
                                    "text_block",
                                    "bullet_list",
                                    "header",
                                    "footer",
                                    "image",
                                    "icon",
                                    "logo",
                                    "chart",
                                    "shape",
                                    "character",
                                    "background_element",
                                ],
                                "description": "Type of visual component",
                            },
                            "label": {
                                "type": "string",
                                "description": "Human-readable label for the component",
                            },
                            "text_content": {
                                "type": "string",
                                "description": "Exact text content if readable, omit otherwise",
                            },
                            "bounding_box": {
                                "type": "object",
                                "description": "Bounding box in pixels",
                                "properties": {
                                    "left": {
                                        "type": "number",
                                        "description": "Pixels from left edge",
                                    },
                                    "top": {
                                        "type": "number",
                                        "description": "Pixels from top edge",
                                    },
                                    "width": {
                                        "type": "number",
                                        "description": "Width in pixels",
                                    },
                                    "height": {
                                        "type": "number",
                                        "description": "Height in pixels",
                                    },
                                },
                                "required": ["left", "top", "width", "height"],
                            },
                            "z_index": {
                                "type": "integer",
                                "description": "1 for background, 2+ for foreground",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Detection confidence 0.0–1.0",
                            },
                            "styles": {
                                "type": "object",
                                "description": "Estimated visual styles",
                                "properties": {
                                    "font_size": {"type": "string"},
                                    "font_weight": {
                                        "type": "string",
                                        "enum": ["normal", "bold", "light"],
                                    },
                                    "color": {
                                        "type": "string",
                                        "description": "#RRGGBB hex color",
                                    },
                                    "background_color": {
                                        "type": "string",
                                        "description": "#RRGGBB hex color or null",
                                    },
                                    "text_align": {
                                        "type": "string",
                                        "enum": ["left", "center", "right"],
                                    },
                                },
                            },
                        },
                        "required": ["component_type", "label", "bounding_box"],
                    },
                },
            },
            "required": ["components"],
        },
    },
}


class NanoBananaService:
    """Unified service for Nano Banana design mode operations.

    Orchestrates vision detection, image regeneration, overlay generation,
    and version management.
    """

    def __init__(
        self,
        *,
        repo: NanoBananaRepository,
        llm_execution_service: LLMExecutionService,
        llm_config: LLMConfig,
    ) -> None:
        self._repo = repo
        self._llm_execution_service = llm_execution_service
        self._llm_config = llm_config
        self._slide_gen_config = None

    @property
    def slide_generation_config(self):
        """Lazy-load SlideGenerationConfig."""
        if self._slide_gen_config is None:
            from ii_agent_tools.integrations.slide_generation.config import (
                SlideGenerationConfig,
            )

            self._slide_gen_config = SlideGenerationConfig()
        return self._slide_gen_config

    # ==================== Detection ====================

    async def detect_components(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: DetectRequest,
    ) -> DetectResponse:
        """Detect visual components in a slide image using vision LLM."""
        await self._repo.validate_session_access(
            db, session_id=request.session_id, user_id=user_id
        )

        try:
            components, img_width, img_height = await self._run_detection(
                image_url=request.image_url,
            )

            overlay_html = None
            if components:
                overlay_html = self._build_overlay_html(
                    image_url=request.image_url,
                    components=components,
                    slide_number=request.slide_number,
                    image_width=img_width,
                    image_height=img_height,
                )

            return DetectResponse(
                success=True,
                slide_number=request.slide_number,
                components=components,
                image_width=img_width,
                image_height=img_height,
                overlay_html=overlay_html,
                cached=False,
            )

        except Exception as e:
            logger.error("[NanoBanana] Detection failed: %s", e)
            return DetectResponse(
                success=False,
                slide_number=request.slide_number,
                error=f"Detection failed: {e!s}",
            )

    # ==================== Regeneration ====================

    async def regenerate_slide(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: RegenerateRequest,
    ) -> RegenerateResponse:
        """Regenerate a slide image with user-specified modifications."""
        await self._repo.validate_session_access(
            db, session_id=request.session_id, user_id=user_id
        )

        if not request.instructions:
            return RegenerateResponse(success=False, error="No instructions provided")

        try:
            result = await self._run_regeneration(
                original_image_url=request.current_image_url,
                instructions=request.instructions,
                components=request.detected_components,
            )

            if not result.get("success"):
                return RegenerateResponse(
                    success=False, error=result.get("error", "Regeneration failed")
                )

            new_image_url = result["url"]
            edit_summary = _build_edit_summary(request.instructions)

            version = await self._repo.create_version(
                db,
                session_id=request.session_id,
                presentation_name=request.presentation_name,
                slide_number=request.slide_number,
                image_url=new_image_url,
                instructions=request.instructions,
                edit_summary=edit_summary,
            )

            await self._repo.update_slide_content_image(
                db,
                session_id=request.session_id,
                presentation_name=request.presentation_name,
                slide_number=request.slide_number,
                image_url=new_image_url,
            )

            return RegenerateResponse(
                success=True,
                new_image_url=new_image_url,
                new_version_id=version.id,
                version_number=version.version,
            )

        except Exception as e:
            logger.error("[NanoBanana] Regeneration failed: %s", e)
            return RegenerateResponse(success=False, error=str(e))

    # ==================== Background Removal ====================

    async def remove_background(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: RemoveBackgroundRequest,
    ) -> RemoveBackgroundResponse:
        """Remove the background from a slide image."""
        await self._repo.validate_session_access(
            db, session_id=request.session_id, user_id=user_id
        )

        try:
            result = await self._run_background_removal(request.image_url)

            if not result.get("success"):
                return RemoveBackgroundResponse(
                    success=False, error=result.get("error", "Background removal failed")
                )

            new_image_url = result["url"]

            version = await self._repo.create_version(
                db,
                session_id=request.session_id,
                presentation_name=request.presentation_name,
                slide_number=request.slide_number,
                image_url=new_image_url,
                edit_summary="Removed background",
            )

            await self._repo.update_slide_content_image(
                db,
                session_id=request.session_id,
                presentation_name=request.presentation_name,
                slide_number=request.slide_number,
                image_url=new_image_url,
            )

            return RemoveBackgroundResponse(
                success=True,
                new_image_url=new_image_url,
                new_version_id=version.id,
            )

        except Exception as e:
            logger.error("[NanoBanana] Background removal failed: %s", e)
            return RemoveBackgroundResponse(success=False, error=str(e))

    # ==================== Version Management ====================

    async def get_versions(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        presentation_name: str,
        slide_number: int,
    ) -> GetVersionsResponse:
        """Get version history for a slide."""
        await self._repo.validate_session_access(
            db, session_id=session_id, user_id=user_id
        )

        try:
            slide = await self._repo.get_slide(
                db,
                session_id=session_id,
                presentation_name=presentation_name,
                slide_number=slide_number,
            )

            current_image_url = None
            if slide:
                current_image_url = extract_image_url_from_slide_html(
                    slide.slide_content or ""
                )

            versions = await self._repo.get_versions(
                db,
                session_id=session_id,
                presentation_name=presentation_name,
                slide_number=slide_number,
            )

            current_version_id = None
            version_infos = []

            for v in versions:
                is_current = v.image_url == current_image_url
                if is_current:
                    current_version_id = v.id

                version_infos.append(
                    SlideVersionInfo(
                        id=v.id,
                        version=v.version,
                        image_url=v.image_url,
                        thumbnail_url=v.thumbnail_url,
                        edit_summary=v.edit_summary,
                        created_at=v.created_at.isoformat(),
                        is_current=is_current,
                    )
                )

            return GetVersionsResponse(
                versions=version_infos,
                current_version_id=current_version_id,
            )

        except Exception as e:
            logger.error("[NanoBanana] Failed to get versions: %s", e)
            return GetVersionsResponse(versions=[], current_version_id=None)

    async def revert_to_version(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request: RevertRequest,
    ) -> RevertResponse:
        """Revert a slide to a previous version.

        Creates a new version with the same image as the target version,
        preserving full history.
        """
        await self._repo.validate_session_access(
            db, session_id=request.session_id, user_id=user_id
        )

        try:
            target = await self._repo.get_version_by_id(
                db, version_id=request.target_version_id
            )
            if not target:
                return RevertResponse(success=False, error="Target version not found")

            if (
                target.session_id != request.session_id
                or target.presentation_name != request.presentation_name
                or target.slide_number != request.slide_number
            ):
                return RevertResponse(
                    success=False,
                    error="Version does not belong to the specified slide",
                )

            new_version = await self._repo.create_version(
                db,
                session_id=request.session_id,
                presentation_name=request.presentation_name,
                slide_number=request.slide_number,
                image_url=target.image_url,
                edit_summary=f"Reverted to version {target.version}",
            )

            await self._repo.update_slide_content_image(
                db,
                session_id=request.session_id,
                presentation_name=request.presentation_name,
                slide_number=request.slide_number,
                image_url=target.image_url,
            )

            return RevertResponse(
                success=True,
                new_version_id=new_version.id,
                new_image_url=target.image_url,
            )

        except Exception as e:
            logger.error("[NanoBanana] Revert failed: %s", e)
            return RevertResponse(success=False, error=str(e))

    # ==================== Internal: Vision Detection ====================

    async def _run_detection(
        self,
        image_url: str,
    ) -> Tuple[List[DetectedComponent], int, int]:
        """Detect visual components in a slide image via LLM tool calling."""
        image_bytes, mime_type = await self._download_image(image_url)
        width, height = self._get_image_dimensions(image_bytes)

        prompt = COMPONENT_DETECTION_PROMPT.format(width=width, height=height)

        client = self._llm_execution_service.create_client(self._llm_config)
        messages = [
            self._llm_execution_service.new_message(
                role=MessageRole.USER,
                session_id="nano-banana-detect",
                parts=[
                    BinaryContent(path="slide-image", mime_type=mime_type, data=image_bytes),
                    TextContent(text=prompt),
                ],
            )
        ]

        response = await self._llm_execution_service.send_once(
            client=client,
            messages=messages,
            tools=[DETECT_COMPONENTS_TOOL],
            provider_options={
                "gemini": {
                    # Override the chat system prompt with a focused detection instruction
                    "system_instruction": (
                        "You are a vision analysis system that detects visual "
                        "components in presentation slide images. "
                        "Always call the provided tool with your results."
                    ),
                    # Disable thinking for faster, deterministic detection
                    "thinking_config": None,
                },
            },
        )

        # Extract the structured payload from the tool call
        for part in response.content or []:
            if isinstance(part, ToolCall) and part.name == _DETECT_TOOL_NAME:
                payload = self._llm_execution_service.parse_tool_input(part.input)
                raw_components = payload.get("components", [])
                components = _build_components(raw_components, width, height)
                logger.info(
                    "[NanoBanana] Detected %d components in slide image",
                    len(components),
                )
                return components, width, height

        logger.warning("[NanoBanana] LLM did not call the detection tool")
        return [], width, height

    # ==================== Internal: Image Regeneration ====================

    async def _run_regeneration(
        self,
        original_image_url: str,
        instructions: List[Instruction],
        components: Optional[List[DetectedComponent]] = None,
    ) -> Dict:
        """Regenerate a slide image with modifications."""
        from ii_agent_tools.integrations.slide_generation.gemini_slide_generator import (
            GeminiSlideGenerationClient,
        )

        prompt = build_regeneration_prompt(instructions, components)
        generator = GeminiSlideGenerationClient(config=self.slide_generation_config)

        try:
            result = await generator.generate_slide(
                full_prompt=prompt,
                reference_image_urls=[original_image_url],
            )

            return {
                "success": True,
                "url": result.url,
                "storage_path": result.storage_path,
                "size": result.size,
                "mime_type": result.mime_type,
            }
        except Exception as e:
            logger.error("[NanoBanana] Image regeneration failed: %s", e)
            return {"success": False, "url": None, "error": str(e)}

    async def _run_background_removal(self, image_url: str) -> Dict:
        """Remove background from a slide image."""
        from ii_agent_tools.integrations.slide_generation.gemini_slide_generator import (
            GeminiSlideGenerationClient,
        )

        generator = GeminiSlideGenerationClient(config=self.slide_generation_config)

        try:
            result = await generator.generate_slide(
                full_prompt=REMOVE_BACKGROUND_PROMPT,
                reference_image_urls=[image_url],
            )

            return {
                "success": True,
                "url": result.url,
                "storage_path": result.storage_path,
            }
        except Exception as e:
            logger.error("[NanoBanana] Background removal failed: %s", e)
            return {"success": False, "url": None, "error": str(e)}

    # ==================== Internal: Overlay HTML ====================

    def _build_overlay_html(
        self,
        image_url: str,
        components: List[DetectedComponent],
        slide_number: int,
        image_width: int = 1280,
        image_height: int = 720,
    ) -> str:
        """Build HTML overlay with image background and positioned component divs."""
        container_width = 1280
        container_height = 720

        # Calculate letterboxing if aspect ratios differ
        container_aspect = container_width / container_height
        image_aspect = image_width / image_height if image_height > 0 else container_aspect

        if image_aspect >= container_aspect:
            display_width = float(container_width)
            display_height = float(container_width) / float(image_aspect)
            offset_left = 0.0
            offset_top = (float(container_height) - display_height) / 2.0
        else:
            display_height = float(container_height)
            display_width = float(container_height) * float(image_aspect)
            offset_top = 0.0
            offset_left = (float(container_width) - display_width) / 2.0

        component_divs = []
        for comp in components:
            div_html = self._build_component_div(
                comp,
                slide_number,
                container_width,
                container_height,
                display_width,
                display_height,
                offset_left,
                offset_top,
            )
            component_divs.append(div_html)

        divs_html = "\n".join(component_divs)
        escaped_image_url = html_escape(image_url, quote=True)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="slide-type" content="nano-banana-overlay">
    <meta name="slide-number" content="{slide_number}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            width: {container_width}px;
            height: {container_height}px;
            overflow: hidden;
            position: relative;
            background-color: #000;
            background-image: url('{escaped_image_url}');
            background-size: contain;
            background-position: center center;
            background-repeat: no-repeat;
        }}
    </style>
</head>
<body data-is-nano-banana-overlay="true" data-slide-number="{slide_number}">
{divs_html}
</body>
</html>"""

        return _inject_runtime_script(html)

    @staticmethod
    def _build_component_div(
        comp: DetectedComponent,
        slide_number: int,
        container_width: float,
        container_height: float,
        display_width: float,
        display_height: float,
        offset_left: float,
        offset_top: float,
    ) -> str:
        """Build a single component div element."""
        bb = comp.bounding_box
        escaped_text = html_escape(comp.text_content or "")
        escaped_label = html_escape(comp.label)

        # Convert from % of image -> % of container (accounting for letterboxing)
        left_px = offset_left + (float(bb.x) / 100.0) * display_width
        top_px = offset_top + (float(bb.y) / 100.0) * display_height
        width_px = (float(bb.width) / 100.0) * display_width
        height_px = (float(bb.height) / 100.0) * display_height

        adj_x = max(0.0, min(100.0, (left_px / float(container_width)) * 100.0))
        adj_y = max(0.0, min(100.0, (top_px / float(container_height)) * 100.0))
        adj_w = max(0.0, min(100.0, (width_px / float(container_width)) * 100.0))
        adj_h = max(0.0, min(100.0, (height_px / float(container_height)) * 100.0))

        style_parts = [
            "position: absolute",
            f"left: {adj_x}%",
            f"top: {adj_y}%",
            f"width: {adj_w}%",
            f"height: {adj_h}%",
            f"z-index: {comp.z_index}",
            "cursor: pointer",
            "box-sizing: border-box",
        ]

        is_text_component = comp.component_type in TEXT_COMPONENT_TYPES or bool(
            (comp.text_content or "").strip()
        )

        if is_text_component and comp.styles:
            if comp.styles.font_size:
                style_parts.append(f"font-size: {comp.styles.font_size}")
            if comp.styles.font_weight:
                style_parts.append(f"font-weight: {comp.styles.font_weight}")
            if comp.styles.text_align:
                style_parts.append(f"text-align: {comp.styles.text_align}")
            if comp.styles.color:
                style_parts.append(f"color: {comp.styles.color}")

        # Hide text by default (shown only on selection)
        if is_text_component:
            style_parts.append("-webkit-text-fill-color: transparent")
            style_parts.append("overflow: hidden")
            style_parts.append("white-space: pre-wrap")
            inner_html = escaped_text
        else:
            inner_html = ""

        div_style = "; ".join(style_parts)

        return (
            f'    <div data-design-id="{comp.design_id}" '
            f'data-component-type="{comp.component_type}" '
            f'data-slide-number="{slide_number}" '
            f'data-label="{escaped_label}" '
            f'style="{div_style}">{inner_html}</div>'
        )

    # ==================== Internal: Helpers ====================

    @staticmethod
    async def _download_image(url: str) -> Tuple[bytes, str]:
        """Download image from URL."""
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            mime_type = response.headers.get("content-type", "").split(";")[0].strip()
            if not mime_type or not mime_type.startswith("image/"):
                mime_type = "image/png"
            return response.content, mime_type

    @staticmethod
    def _get_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
        """Get image dimensions from bytes."""
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                return img.size
        except Exception:
            return 1280, 720  # Default slide dimensions


# ============ Module-Level Helpers ============


def _build_components(
    raw_components: list[dict[str, Any]],
    img_width: int,
    img_height: int,
) -> List[DetectedComponent]:
    """Convert raw tool-call component dicts into DetectedComponent list."""
    if not isinstance(raw_components, list):
        logger.error("[NanoBanana] Detection payload 'components' is not a list")
        return []

    components: List[DetectedComponent] = []
    type_counters: Dict[str, int] = {}

    for raw in raw_components:
        if not isinstance(raw, dict):
            continue

        comp_type = raw.get("component_type", "unknown")
        idx = type_counters.get(comp_type, 0)
        type_counters[comp_type] = idx + 1
        design_id = f"nano-{comp_type}-{idx}"

        bbox = _parse_bounding_box(raw.get("bounding_box", {}), img_width, img_height)
        if not bbox:
            logger.warning(
                "[NanoBanana] Invalid bounding box for %s, skipping", design_id
            )
            continue

        styles = _parse_styles(raw.get("styles"))

        components.append(
            DetectedComponent(
                design_id=design_id,
                component_type=comp_type,
                label=str(raw.get("label", comp_type)),
                text_content=raw.get("text_content"),
                bounding_box=bbox,
                z_index=int(raw.get("z_index", 1)),
                confidence=float(raw.get("confidence", 0.0)),
                styles=styles,
            )
        )

    return components


def _inject_runtime_script(html: str) -> str:
    """Inject design mode runtime script and fonts into HTML."""
    injection = f"{DESIGN_MODE_GOOGLE_FONTS}\n{DESIGN_MODE_RUNTIME_SCRIPT}"

    if "<head>" in html:
        return html.replace("<head>", f"<head>\n{injection}\n", 1)
    if "<head " in html:
        return re.sub(
            r"(<head[^>]*>)",
            lambda m: f"{m.group(1)}\n{injection}\n",
            html,
            count=1,
        )
    if "<html>" in html or "<html " in html:
        return re.sub(
            r"(<html[^>]*>)",
            lambda m: f"{m.group(1)}\n<head>\n{injection}\n</head>\n",
            html,
            count=1,
        )
    return f"{injection}\n{html}"


def _parse_bounding_box(
    bb_raw: dict, img_width: int, img_height: int
) -> Optional[BoundingBox]:
    """Parse bounding box from detection response, converting pixels to percentages."""
    if not isinstance(bb_raw, dict):
        return None

    try:
        left = float(bb_raw.get("left", bb_raw.get("x", 0)))
        top = float(bb_raw.get("top", bb_raw.get("y", 0)))
        width = float(bb_raw.get("width", bb_raw.get("w", 0)))
        height = float(bb_raw.get("height", bb_raw.get("h", 0)))

        if width <= 0 and "right" in bb_raw:
            width = float(bb_raw["right"]) - left
        if height <= 0 and "bottom" in bb_raw:
            height = float(bb_raw["bottom"]) - top

        if width <= 0 or height <= 0:
            return None

        x_pct = (left / img_width) * 100.0
        y_pct = (top / img_height) * 100.0
        w_pct = (width / img_width) * 100.0
        h_pct = (height / img_height) * 100.0

        return BoundingBox(
            x=max(0, min(100, x_pct)),
            y=max(0, min(100, y_pct)),
            width=max(0.1, min(100, w_pct)),
            height=max(0.1, min(100, h_pct)),
        )
    except (TypeError, ValueError):
        return None


def _parse_styles(styles_raw: Optional[dict]) -> Optional[ComponentStyles]:
    """Parse component styles from detection response."""
    if not isinstance(styles_raw, dict):
        return None

    return ComponentStyles(
        font_size=styles_raw.get("font_size"),
        font_weight=styles_raw.get("font_weight"),
        color=styles_raw.get("color"),
        background_color=styles_raw.get("background_color"),
        text_align=styles_raw.get("text_align"),
    )


def _build_edit_summary(instructions: list[Instruction]) -> str:
    """Build a human-readable summary of edit instructions."""
    if not instructions:
        return "No changes"

    summaries = []
    for inst in instructions:
        if inst.instruction_type.value == "text_edit":
            summaries.append("Text edit")
        elif inst.instruction_type.value == "ai_modify":
            prompt = inst.ai_prompt or ""
            if len(prompt) > 50:
                prompt = prompt[:47] + "..."
            summaries.append(f"AI: {prompt}")
        elif inst.instruction_type.value == "remove_background":
            summaries.append("Remove background")

    if len(summaries) == 1:
        return summaries[0]
    elif len(summaries) <= 3:
        return ", ".join(summaries)
    else:
        return f"{len(summaries)} changes"
