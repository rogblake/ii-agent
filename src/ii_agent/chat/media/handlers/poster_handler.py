"""Handler for poster generation media type."""

from __future__ import annotations

import mimetypes
import uuid
from typing import TYPE_CHECKING, List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import (
    BinaryContent,
    MediaPreferences,
    TextContent,
)
from ii_agent.chat.tools.image_generate import ImageGenerationTool
from ..modes.base import BaseModeStrategy
from ..modes.normal_mode import NormalModeStrategy
from ..modes.template_reference_mode import TemplateReferenceModeStrategy
from ..registry import register_handler
from ..utils import PromptBuilder
from .base import BaseMediaHandler

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer


@register_handler("poster")
class PosterMediaHandler(BaseMediaHandler):
    """
    Handler for poster generation.

    Uses the image generation tool but has its own media handler so
    poster routing is isolated from standard image mode.
    """

    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        # Template-based generation (styles) uses TemplateReferenceModeStrategy
        if media_preferences.template_id is not None:
            # Keep context for follow-up messages while still applying template guidance
            return TemplateReferenceModeStrategy(clear_context=False)

        return NormalModeStrategy()

    async def create_tools(
        self,
        *,
        session_id: uuid.UUID,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
        container: ApplicationContainer,
    ) -> list[ImageGenerationTool]:
        return [
            ImageGenerationTool(
                session_id=session_id,
                media_preferences=media_preferences,
                image_aspect_ratio=media_preferences.aspect_ratio,
                image_resolution=media_preferences.resolution,
                references=None,
                mini_tools_mode=False,
                container=container,
            )
        ]

    async def build_llm_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
    ) -> List[BinaryContent | TextContent]:
        if not isinstance(mode_strategy, TemplateReferenceModeStrategy):
            return []

        template_url = await mode_strategy.get_template_preview_url(
            db_session=db_session,
            session_id=session_id,
            media_preferences=media_preferences,
        )
        if not template_url:
            return []

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(template_url)
                response.raise_for_status()
                file_bytes = response.content
                mime_type = response.headers.get("content-type")
        except Exception:
            return []

        if not mime_type:
            mime_type = mimetypes.guess_type(template_url)[0] or "application/octet-stream"

        return [
            TextContent(
                text=(
                    "\n STYLE REFERENCE IMAGE #1 - COPY STYLE ONLY "
                    "(colors, typography feel, layout rhythm, textures). "
                    "DO NOT copy any specific text, logos, characters, or layout."
                )
            ),
            BinaryContent(
                path=template_url,
                mime_type=mime_type,
                data=file_bytes,
            ),
        ]

    async def build_tool_hint(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
        mode_strategy: BaseModeStrategy,
    ) -> str:
        # Build mode-specific prompt context
        mode_context = await mode_strategy.build_prompt_context(
            db_session=db_session,
            session_id=session_id,
            media_preferences=media_preferences,
        )

        settings_constraint = PromptBuilder.build_settings_constraint(
            aspect_ratio=media_preferences.aspect_ratio,
            resolution=media_preferences.resolution,
        )

        poster_prompt_guidance = (
            "\n\n[Poster prompt guidance: Your prompt to generate_image MUST include all of the following "
            "poster requirements directly in the prompt text:\n"
            '- Start with an explicit poster instruction (e.g., "Design a bold poster for ...")\n'
            "- Single clear concept; one focal subject or typography-driven hero\n"
            "- Always include a main title; if the user does not provide one, generate a concise title in the user's language\n"
            "- Include a subtitle/tagline and key details only if provided (date, time, location, CTA); do NOT invent specifics\n"
            "- Strong hierarchy: title > subtitle > details > CTA; use large, readable type\n"
            "- Keep text minimal: short phrases only; no paragraphs\n"
            "- Layout: centered or grid-aligned composition, balanced negative space, clear reading order\n"
            "- Full-bleed or deliberate margins; avoid floating card, split panels, or multi-page layout\n"
            "- Use the full canvas: edge-to-edge composition with no large empty margins or unused outer area\n"
            "- Keep a continuous background across the whole canvas; avoid heavy borders, frames, or inset cards\n"
            "- Negative constraints: no centered floating card, no thick outline border, no inner frame, no drop-shadowed panel, no rounded-corner poster inside a background\n"
            "- No mockup or presentation frame: the poster IS the full canvas (do not place it on a separate background)\n"
            "- Do NOT add outer gutters/margins; all design elements should feel integrated with the edge-to-edge background\n"
            "- Do NOT draw any border/outline/stroke/frame lines around the poster or inside it (no thin gold frame, no keyline, no inset border)\n"
            "- If the style reference includes a frame or border, IGNORE those frame elements and keep the design full-bleed\n"
            "- Use visual emphasis to spotlight the main title or hero element\n"
            "- Typography: 1-2 fonts max, bold display + clean support; clear hierarchy and consistent alignment\n"
            "- Correct text rendering: quote all exact labels/callouts verbatim (or spell letter-by-letter) in the prompt\n"
            "- Legible text with correct spelling and grammar\n"
            "- Language: Detect the user's request language and render ALL poster text in that language, unless the user explicitly requests a different language\n"
            "- Cohesive color palette with limited hues; strong contrast; use brand colors if specified\n"
            "- Imagery, icons, and graphic elements must share a consistent style and line weight\n"
            "- Premium, print-ready finish: crisp edges, clean spacing, polished composition\n"
            "- Quality: request highest quality for text-heavy posters\n"
            "- Constraints: no watermark, no handwritten fonts unless explicitly requested\n"
            "Follow any user/template style if specified; otherwise choose a subject-appropriate poster style and palette inferred from the topic. "
            "If no strong cues exist, default to a refined modern poster style: bold headline, clean geometry, controlled accents, and ample whitespace.\n"
            "IMPORTANT: Embed these requirements directly in your prompt — the image tool will NOT add them automatically.]"
        )

        return (
            f"\n\n[User selected media generation: "
            f"type={media_preferences.type}, "
            f"model_name={media_preferences.model_name}. "
            f"You MUST call the generate_image tool immediately. "
            f"Your response MUST be only a generate_image tool call (no prose). "
            f"The final output must include the generated image; "
            f"text-only responses are NOT allowed.]"
            f"{settings_constraint}"
            f"{mode_context}"
            f"{poster_prompt_guidance}"
        )
