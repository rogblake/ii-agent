"""Manga generation tool — subclass of StorybookGenerationTool with manga-specific overrides."""

from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

from ii_agent.chat.schemas import MediaPreferences
from .storybook_generate import StorybookGenerationTool

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


class MangaGenerationTool(StorybookGenerationTool):
    """Generate manga-style illustrated storybooks with multi-panel layouts."""

    def __init__(
        self,
        session_id: str,
        *,
        container: ServiceContainer,
        media_preferences: Optional[MediaPreferences] = None,
    ):
        super().__init__(
            session_id,
            container=container,
            media_preferences=media_preferences,
        )
        # Force manga constraints
        self.manga_layout = True
        self.user_text_position = "none"
        self.voice_enabled = False

    def _build_style_context(self, style: dict[str, Any]) -> str:
        """Build style context with manga-specific art style and color rules."""
        style_parts = []

        character_description = style.get("character_description")
        art_style = style.get("art_style")
        color_palette = style.get("color_palette")

        if character_description:
            style_parts.append(f"Character: {character_description}")

        if art_style:
            style_parts.append(f"Art style: {art_style}")

        if color_palette:
            style_parts.append(f"Color palette: {color_palette}")

        # Manga-specific art style defaults
        art_style_value = str(art_style or "").strip()
        art_style_lower = art_style_value.lower()
        color_palette_value = str(color_palette or "").strip()
        color_palette_lower = color_palette_value.lower()

        if not art_style_value:
            style_parts.append(
                "Art style: traditional Japanese manga line art with clean black-and-white ink and screentone shading"
            )
        elif "manga" not in art_style_lower and "comic" not in art_style_lower:
            style_parts.append(
                "Manga treatment: clean ink line art, consistent line weight, screentone shading"
            )

        # Monochrome detection
        is_monochrome = False
        if color_palette_value:
            if (
                "monochrome" in color_palette_lower
                or "grayscale" in color_palette_lower
                or "grey scale" in color_palette_lower
            ):
                is_monochrome = True
            else:
                has_black = "black" in color_palette_lower
                has_white = "white" in color_palette_lower
                has_gray = "gray" in color_palette_lower or "grey" in color_palette_lower
                if (has_black and has_white) or has_gray:
                    is_monochrome = True

        if not color_palette_value or is_monochrome:
            style_parts.append(
                "Color palette: STRICTLY monochrome black and white only — no color whatsoever. "
                "No colored backgrounds, no colored effects, no colored highlights, no tinted panels, "
                "no sepia, no colored speech bubbles. Use only black ink, white space, and gray screentone shading"
            )
        else:
            style_parts.append(
                f"Color palette: apply '{color_palette_value}' uniformly to EVERY page — "
                "no page should fall back to grayscale or use different colors"
            )

        style_parts.append(
            "Consistency: identical line weight, screentone density, contrast, and color treatment across ALL pages"
        )

        return ". ".join(style_parts) if style_parts else ""

    def _enhance_prompt_with_style(
        self,
        image_prompt: str,
        style_context: str,
        is_cover_page: bool = False,
        reference_type: Optional[str] = None,
        composition_rule: Optional[str] = None,
    ) -> str:
        """Enhance image prompt with manga-specific color enforcement."""
        enhanced = super()._enhance_prompt_with_style(
            image_prompt,
            style_context,
            is_cover_page=is_cover_page,
            reference_type=reference_type,
            composition_rule=composition_rule,
        )

        # Manga-specific: enforce consistent color treatment
        has_explicit_color = style_context and "apply '" in style_context
        if not has_explicit_color:
            enhanced += (
                " MANGA COLOR ENFORCEMENT: This is a black-and-white manga page. "
                "STRICTLY PROHIBITED: any color, colored elements, colored backgrounds, "
                "colored highlights, colored effects, tinted panels, sepia tones, "
                "colored speech bubbles, or any chromatic content. "
                "Use ONLY black ink lines, white space, and gray screentone shading."
            )

        return enhanced

    def _augment_non_cover_prompt(
        self, image_prompt: str, text_content: str
    ) -> str:
        """Inject speech bubble text into the image prompt for manga pages."""
        if text_content:
            language_label = self.storybook_language or "the selected language"
            return (
                f"{image_prompt}\nIMPORTANT: Include speech bubbles or caption boxes "
                f"with readable {language_label} text. Use this exact dialogue text: "
                f'"{text_content}". Keep the text concise and legible.'
            )
        return image_prompt
