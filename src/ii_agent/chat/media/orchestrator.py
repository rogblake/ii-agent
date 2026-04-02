"""Media generation orchestrator."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.schemas import (
    BinaryContent,
    TextContent,
    ChatMessageRequest,
    MediaPreferences,
    MediaReference,
    AdvancedModeState,
)
from ii_agent.chat.tools import BaseTool
from .registry import get_handler
from .utils import AdvancedModeStateManager

if TYPE_CHECKING:
    from ii_agent.core.container import ServiceContainer

logger = logging.getLogger(__name__)


@dataclass
class MediaContext:
    """
    Context for media generation.

    Contains all necessary components for media generation including tool instance,
    LLM message parts, and configuration.
    """

    tool_name: str                                  # e.g., "generate_image"
    tool_instance: BaseTool                         # Configured tool (e.g., ImageGenerationTool)
    llm_message_parts: List[BinaryContent | TextContent]  # Reference images with labels
    tool_hint: str                                  # Prompt context to append to user message
    should_clear_context: bool                      # Whether to clear conversation context


class MediaOrchestrator:
    """
    Orchestrates media generation across different types and modes.

    This is the single entry point that service.py should interact with for all
    media generation functionality.
    """

    @classmethod
    def get_default_media_preferences(cls, media_type: str = "image") -> MediaPreferences:
        """
        Get default media preferences for chat mode.

        Args:
            media_type: Type of media ("image" or "video")

        Returns:
            MediaPreferences with sensible defaults
        """
        return MediaPreferences(
            enabled=True,
            type=media_type,
            model_name="gemini-3-pro-image-preview",  # Default to Gemini 3 Pro image model
            provider="gemini",
            aspect_ratio="1:1",
            resolution="1K",
        )

    @classmethod
    async def prepare_default_media_tool(
        cls,
        *,
        session_id: str,
        media_type: str = "image",
        container: ServiceContainer,
    ) -> BaseTool:
        """
        Prepare a simple media generation tool for chat mode without full context.

        This is used when generate_image is enabled in chat mode but no explicit
        media_preferences were provided. Creates a lightweight tool instance with
        default settings.

        Args:
            session_id: Current session ID
            media_type: Type of media to generate ("image" or "video")

        Returns:
            BaseTool instance ready for use
        """
        # Get handler for media type
        handler_class = get_handler(media_type)
        if not handler_class:
            from .registry import list_handlers
            logger.error(f"[MEDIA] No handler registered for media type: {media_type}")
            logger.error(f"[MEDIA] Available handlers: {list_handlers()}")
            raise ValueError(f"No handler registered for media type: {media_type}")

        handler = handler_class()

        # Get default preferences
        default_prefs = cls.get_default_media_preferences(media_type)

        # Detect mode (will be NormalMode since no advanced/mini tools)
        mode_strategy = handler.detect_mode(default_prefs)

        # Create simple tool instance
        tool = await handler.create_tool(
            session_id=session_id,
            mode_strategy=mode_strategy,
            media_preferences=default_prefs,
            container=container,
        )

        logger.info(
            f"[CHAT_MODE] Created default {media_type} generation tool with defaults: "
            f"model={default_prefs.model_name}, provider={default_prefs.provider}"
        )

        return tool

    @classmethod
    async def prepare_media_context(
        cls,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
        chat_request: ChatMessageRequest,
        container: ServiceContainer,
    ) -> MediaContext:
        """
        Prepare media generation context (messages, tools, metadata).

        Args:
            db_session: Database session
            session_id: Current session ID
            media_preferences: User's media generation preferences
            chat_request: Full chat request object

        Returns:
            MediaContext with tool instance, LLM parts, and configuration

        Raises:
            ValueError: If media type handler is not registered
        """
        # 1. Get handler for media type
        handler_class = get_handler(media_preferences.type)
        if not handler_class:
            from .registry import list_handlers
            logger.error(f"[MEDIA] No handler registered for media type: {media_preferences.type}")
            logger.error(f"[MEDIA] Available handlers: {list_handlers()}")
            raise ValueError(f"No handler registered for media type: {media_preferences.type}")

        handler = handler_class()
        logger.debug(f"[MEDIA] Created handler instance: {handler.__class__.__name__}")
        logger.info(f"[MEDIA] Using handler: {handler_class.__name__}")

        # 2. Let handler detect its own mode (media-type-specific)
        mode_strategy = handler.detect_mode(media_preferences)
        logger.info(f"[MEDIA] Detected mode: {mode_strategy.get_mode_name()}")

        # 3. Create tool instance
        tool = await handler.create_tool(
            session_id=session_id,
            mode_strategy=mode_strategy,
            media_preferences=media_preferences,
            container=container,
        )

        # 4. Build LLM context (reference images, labels)
        llm_parts = await handler.build_llm_context(
            db_session=db_session,
            session_id=session_id,
            mode_strategy=mode_strategy,
            media_preferences=media_preferences,
        )
        logger.info(f"[MEDIA] Built {len(llm_parts)} LLM message parts")

        # 5. Build tool hint
        tool_hint = await handler.build_tool_hint(
            db_session=db_session,
            session_id=session_id,
            media_preferences=media_preferences,
            mode_strategy=mode_strategy,
        )

        return MediaContext(
            tool_name=tool.name,
            tool_instance=tool,
            llm_message_parts=llm_parts,
            tool_hint=tool_hint,
            should_clear_context=mode_strategy.should_clear_context(),
        )

    @classmethod
    async def get_advanced_mode_state(
        cls,
        *,
        db_session: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> AdvancedModeState:
        """
        Fetch advanced mode state for a session.

        Args:
            db_session: Database session
            session_id: Session ID
            user_id: User ID (for access validation)

        Returns:
            AdvancedModeState with enabled flag and references
        """
        # Note: Access validation should be done in service.py or router
        # before calling this method
        return await AdvancedModeStateManager.get_state(
            db_session=db_session,
            session_id=session_id,
        )

    @classmethod
    async def update_advanced_mode_state(
        cls,
        *,
        db_session: AsyncSession,
        session_id: str,
        user_id: str,
        enabled: bool,
        references: list[MediaReference] | None,
    ) -> AdvancedModeState:
        """
        Persist advanced mode state for a session.

        Args:
            db_session: Database session
            session_id: Session ID
            user_id: User ID (for access validation)
            enabled: Whether advanced mode is enabled
            references: List of MediaReference objects

        Returns:
            Updated AdvancedModeState
        """
        # Note: Access validation should be done in service.py or router
        # before calling this method
        return await AdvancedModeStateManager.update_state(
            db_session=db_session,
            session_id=session_id,
            enabled=enabled,
            references=references,
        )
