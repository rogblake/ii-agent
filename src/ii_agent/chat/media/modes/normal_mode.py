"""Normal mode strategy for media generation."""

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import MediaPreferences
from .base import BaseModeStrategy


class NormalModeStrategy(BaseModeStrategy):
    """
    Normal mode strategy for standard media generation.

    - Does not clear conversation context
    - Minimal prompt additions (just media type and model selection)
    - No special reference handling beyond what's in media_preferences
    """

    def should_clear_context(self) -> bool:
        """Normal mode keeps full conversation context."""
        return False

    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build simple prompt context for normal mode."""
        # In normal mode, we just indicate the media type and model selected
        # No special advanced mode instructions
        return ""

    def get_mode_name(self) -> str:
        """Return mode name for logging."""
        return "normal"
