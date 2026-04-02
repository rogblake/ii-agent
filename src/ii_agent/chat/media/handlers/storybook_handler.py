"""Handler for storybook generation media type."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import (
    BinaryContent,
    TextContent,
    MediaPreferences,
)
from ii_agent.chat.tools.manga_generate import MangaGenerationTool
from ii_agent.chat.tools.storybook_generate import StorybookGenerationTool
from ..modes.base import BaseModeStrategy
from ..modes.manga_mode import MangaModeStrategy
from ..modes.storybook_mode import StorybookModeStrategy
from ..registry import register_handler
from .base import BaseMediaHandler

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer

logger = logging.getLogger(__name__)


@register_handler("storybook")
class StorybookMediaHandler(BaseMediaHandler):
    """
    Handler for storybook generation media type.

    Storybook mode generates multi-scene illustrated stories where each scene
    combines an AI-generated image with narrative text in a user-specified layout.
    """

    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        """Detect mode: manga layout uses MangaModeStrategy, otherwise StorybookModeStrategy."""
        if getattr(media_preferences, "manga_layout", False):
            return MangaModeStrategy()
        return StorybookModeStrategy()

    async def create_tools(
        self,
        *,
        session_id: uuid.UUID,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
        container: ApplicationContainer,
    ) -> list[StorybookGenerationTool]:
        """Create the appropriate generation tool based on the detected mode."""
        if isinstance(mode_strategy, MangaModeStrategy):
            return [
                MangaGenerationTool(
                    session_id=session_id,
                    media_preferences=media_preferences,
                    container=container,
                )
            ]
        return [
            StorybookGenerationTool(
                session_id=session_id,
                media_preferences=media_preferences,
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
        """
        Build LLM message parts for storybook generation.

        Storybook is text-driven (user describes story), so no reference images needed.
        Character consistency is handled via tool parameters, not reference images.
        """
        # No reference images needed for storybook
        return []

    async def build_tool_hint(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
        mode_strategy: BaseModeStrategy,
    ) -> str:
        """Generate tool hint text for storybook generation."""
        # Build mode-specific prompt context
        mode_context = await mode_strategy.build_prompt_context(
            db_session=db_session,
            session_id=session_id,
            media_preferences=media_preferences,
        )

        # Build base storybook hint
        tool_hint = (
            f"\n\n[User selected storybook generation: "
            f"model_name={media_preferences.model_name}. "
            f"You MUST call the generate_storybook tool with an array of scenes. "
            f"Each scene must have: image_prompt, text_content, text_position, and text_percentage. "
            f"IMPORTANT: After calling the tool, DO NOT include image URLs or markdown images in your text response. "
            f"The UI will automatically display the storybook in an interactive viewer.]"
            f"{mode_context}"
        )

        return tool_hint
