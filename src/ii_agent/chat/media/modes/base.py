"""Base class for media generation mode strategies."""

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import MediaPreferences


class BaseModeStrategy(ABC):
    """
    Base strategy for different media generation modes.

    Each mode (advanced, mini tools, normal) defines different behavior for:
    - Context clearing (whether to clear conversation history)
    - Prompt building (how to construct prompts for the LLM)
    """

    @abstractmethod
    def should_clear_context(self) -> bool:
        """
        Determine if conversation context should be cleared for this mode.

        Returns:
            True if context should be cleared, False otherwise
        """
        pass

    @abstractmethod
    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
    ) -> str:
        """
        Build mode-specific prompt context to append to user message.

        Args:
            db_session: Database session
            session_id: Current session ID
            media_preferences: User's media generation preferences

        Returns:
            Formatted prompt context string
        """
        pass

    @abstractmethod
    def get_mode_name(self) -> str:
        """
        Get the name of this mode for logging/debugging.

        Returns:
            Mode name (e.g., "advanced", "mini_tools", "normal")
        """
        pass
