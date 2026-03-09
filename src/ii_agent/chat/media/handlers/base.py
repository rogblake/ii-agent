"""Base class for media type handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import (
    BinaryContent,
    TextContent,
    MediaPreferences,
)
from ii_agent.chat.tools import BaseTool
from ii_agent.chat.media.modes.base import BaseModeStrategy

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer


class BaseMediaHandler(ABC):
    """
    Base handler for media type generation.

    Each media type (image, video, poster) implements this interface to handle:
    - Mode detection specific to this media type
    - Tool creation with type-specific configuration
    - LLM context building (reference media, labels, etc.)
    - Tool hint generation for prompts
    """

    @abstractmethod
    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        """
        Detect which mode strategy to use based on media preferences.

        Each media type can have different modes. For example:
        - Image: AdvancedMode, MiniToolsMode, NormalMode

        Args:
            media_preferences: User's media generation preferences

        Returns:
            Mode strategy appropriate for this media type
        """
        pass

    @abstractmethod
    async def create_tools(
        self,
        *,
        session_id: str,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
        container: ServiceContainer,
    ) -> List[BaseTool]:
        """
        Create configured tool instances for this media type.

        Most handlers return a single tool. Video returns multiple
        (generate, concatenate, extract_frames).

        Args:
            session_id: Current session ID
            mode_strategy: Mode strategy being used
            media_preferences: User's media generation preferences
            container: Service container for dependencies

        Returns:
            List of configured tool instances
        """
        pass

    @abstractmethod
    async def build_llm_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
    ) -> List[BinaryContent | TextContent]:
        """
        Build LLM message parts (reference media, labels, etc.).

        Args:
            db_session: Database session
            session_id: Current session ID
            mode_strategy: Mode strategy being used
            media_preferences: User's media generation preferences

        Returns:
            List of message parts to add to LLM message
        """
        pass

    @abstractmethod
    async def build_tool_hint(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
        mode_strategy: BaseModeStrategy,
    ) -> str:
        """
        Generate tool hint text to append to user message.

        Args:
            db_session: Database session
            session_id: Current session ID
            media_preferences: User's media generation preferences
            mode_strategy: Mode strategy being used

        Returns:
            Formatted tool hint string
        """
        pass
