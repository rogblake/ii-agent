"""Handler for infographic generation media type."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import (
    BinaryContent,
    MediaPreferences,
    TextContent,
)
from ii_agent.chat.tools.image_generate import ImageGenerationTool
from ..modes.base import BaseModeStrategy
from ..modes.mini_tools_mode import MiniToolsModeStrategy
from ..modes.normal_mode import NormalModeStrategy
from ..registry import register_handler
from ..utils import PromptBuilder
from .base import BaseMediaHandler

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer


@register_handler("infographic")
class InfographicMediaHandler(BaseMediaHandler):
    """
    Handler for infographic generation.

    Uses the image generation tool but has its own media handler so
    infographic routing is isolated from standard image mode.
    """

    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        # Template-based generation (styles) uses MiniToolsModeStrategy for prompt context
        if media_preferences.template_id is not None:
            # Keep context for follow-up messages while still applying template guidance
            return MiniToolsModeStrategy(clear_context=False)

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
        # No reference images for infographic mode
        return []

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

        infographic_prompt_guidance = (
            "\n\n[Infographic prompt guidance: Your prompt to generate_image MUST include all of the following "
            "infographic requirements directly in the prompt text:\n"
            '- Start with an explicit infographic instruction (e.g., "Create a detailed infographic titled ...")\n'
            "- Single clear topic/message; if multiple points are provided, synthesize into one focused theme\n"
            "- Always include a main title; if the user does not provide one, generate a concise topic title in the user's language\n"
            "- Title and section headings for every block; group related facts into labeled columns/cards\n"
            "- Organized flow (top-to-bottom or left-to-right); add arrows/connectors for sequences or steps\n"
            "- Choose a layout that matches the data (grid, flowchart, timeline, map, comparison)\n"
            '- Include a unifying "visual backbone" (consistent accent line, frame, or motif) spanning the layout\n'
            "- Use visual separators (lines, background blocks, icons) and balanced whitespace between sections\n"
            "- FULL-BLEED layout that fills the entire frame; avoid large empty margins, thick borders, or floating poster look\n"
            "- Avoid split-panel or page-like layouts; do NOT render the infographic as two separate pages/cards\n"
            "- Keep a continuous background across the whole canvas; no inner frames or heavy borders\n"
            "- Ensure smooth visual continuity between sections; avoid harsh separations or disconnected blocks\n"
            "- Short, readable labels with large text; no paragraphs\n"
            "- Typography: 2-3 fonts max, clear hierarchy (title > subheads > labels), high contrast, consistent alignment\n"
            "- Correct text rendering: quote all exact labels/callouts verbatim (or spell letter-by-letter) in the prompt\n"
            "- Legible text with correct spelling and grammar\n"
            "- Language: Detect the user's request language and render ALL infographic text in that language, unless the user explicitly requests a different language; keep terminology consistent and avoid reflowing provided text\n"
            "- Cohesive color palette with limited hues; strong text contrast; light background with darker text unless subject dictates otherwise; use brand colors if specified; avoid rainbow palettes\n"
            "- Icons, illustrations, and charts must share a consistent style and line weight; each visual has a short label\n"
            "- Charts: pick the chart type that fits the data (pie for proportions, bar for comparisons, line for trends); keep charts simple and readable at a glance\n"
            "- Visual emphasis: highlight key data points with color/size against muted tones\n"
            "- Premium, polished finish: uniform typography, matching icon style, repeated motif; subtle gradients/textures only if controlled and purposeful\n"
            "- Quality: request highest quality for text-heavy infographics\n"
            "- Subject-aware art direction: infer the primary subject (e.g., modern architecture, historical topic, food, nature, tech) and choose a matching palette, typography, and motif; avoid style mismatches\n"
            "- Space optimization: maximize canvas usage with balanced density and purposeful whitespace; avoid unused outer areas\n"
            "- Avoid duplicate information: do not repeat the same fact or label in multiple sections; each point appears once only\n"
            "- Constraints: no watermark, no handwritten fonts\n"
            "Follow any user/template style if specified; otherwise choose a subject-appropriate style and palette inferred from the topic. "
            "If no strong cues exist, default to a refined modern infographic style: soft pastel palette, clean geometry, subtle layered frames, "
            "and detailed yet uncluttered illustrations that enhance comprehension.\n"
            "Ensure content extends to all edges (or a deliberate thin safety margin only); avoid excess background padding or unused outer canvas.\n"
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
            f"{infographic_prompt_guidance}"
        )
