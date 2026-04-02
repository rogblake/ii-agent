"""Advanced mode strategy for media generation."""

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import MediaPreferences
from ..utils import PromptBuilder
from .base import BaseModeStrategy


class AdvancedModeStrategy(BaseModeStrategy):
    """
    Advanced mode strategy for reference-based generation.

    - Keeps full conversation context
    - Builds detailed prompt with reference type guidance
    - Supports subject/scene/style references
    - Includes validation checklist and modification instructions
    """

    def should_clear_context(self) -> bool:
        """Advanced mode keeps full conversation context."""
        return False

    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build comprehensive prompt context for advanced mode."""
        advanced_parts = []

        # Part 1: Reference images guidance (if provided)
        if media_preferences.references:
            guidance_text, image_index_map, next_index = PromptBuilder.build_reference_guidance(
                references=media_preferences.references,
                starting_index=1,
            )
            if guidance_text:
                advanced_parts.append(guidance_text)

            # Part 2: Previously generated images guidance
            previous_images_guidance = PromptBuilder.build_previous_images_guidance(
                starting_index=next_index,
            )
            advanced_parts.append(previous_images_guidance)

            # Part 3: Build dynamic checklist
            checklist = PromptBuilder.build_checklist(
                references=media_preferences.references,
            )
            if checklist:
                advanced_parts.append(checklist)
        else:
            # No references, but still include general guidance
            advanced_parts.append(
                "=== PREVIOUSLY GENERATED IMAGES ===\n"
                "Attached images are previously generated from this conversation.\n"
                "Use the MOST RECENT generated image as the primary reference when user asks for modifications."
            )

        # Combine all parts
        if advanced_parts:
            return (
                "\n\n[ADVANCED MODE - Image Generation Context]\n"
                + "\n\n".join(advanced_parts)
            )

        return ""

    def get_mode_name(self) -> str:
        """Return mode name for logging."""
        return "advanced"
