"""Mini tools mode strategy for media generation."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import MediaPreferences
from ii_agent.core.container import get_app_container
from ..utils import PromptBuilder
from .base import BaseModeStrategy

logger = logging.getLogger(__name__)


class MiniToolsModeStrategy(BaseModeStrategy):
    """
    Mini tools mode strategy for template-based generation.

    - Optionally clears conversation context for fresh generation
    - Retrieves template prompt from database
    - Combines template prompt with user input
    - Optimized for quick, focused generation with templates
    """

    def __init__(self, *, clear_context: bool = True) -> None:
        self._clear_context = clear_context

    def should_clear_context(self) -> bool:
        """Mini tools mode clears context for fresh generation."""
        return self._clear_context

    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: str,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build prompt context for mini tools mode."""
        # Add mini tool hint if present
        tool_fragment = ""
        template_prompt_instruction = ""
        target_id = None
        target_name = None

        if media_preferences.mini_tools:
            mini_tool = media_preferences.mini_tools
            target_id = mini_tool.id
            target_name = mini_tool.name
        elif media_preferences.template_id:
            target_id = media_preferences.template_id
            # Name will be resolved from template if possible.

        if target_id:
            try:
                template = await get_app_container().media_template_service.get_media_template_by_id(db_session, target_id)

                if template:
                    target_name = target_name or template.name

                    if target_name:
                        tool_fragment = PromptBuilder.build_mini_tool_hint(
                            mini_tool_id=target_id,
                            mini_tool_name=target_name,
                        )

                if template and template.prompt and target_name:
                    logger.info(
                        f"[MINI_TOOLS] Retrieved template prompt for '{target_name}' (ID: {target_id})"
                    )
                    # Add template instructions to guide the LLM
                    template_prompt_instruction = (
                        f"\n\n[Mini Tool Template Instructions]\n"
                        f"Template: {target_name}\n"
                        f"Base Guidelines: {template.prompt}\n\n"
                        f"IMPORTANT: Combine the user's request with these template guidelines. "
                        f"Use the template guidelines as the foundation, but adapt based on the user's specific request."
                    )
                elif not template:
                    logger.warning(f"[MINI_TOOLS] Template not found for ID: {target_id}")
                else:
                    logger.info(f"[MINI_TOOLS] Template {target_id} has no prompt")
            except Exception as e:
                logger.error(
                    f"[MINI_TOOLS] Failed to retrieve template prompt for {target_id}: {e}",
                    exc_info=True,
                )

        return tool_fragment + template_prompt_instruction

    def get_mode_name(self) -> str:
        """Return mode name for logging."""
        return "mini_tools"
