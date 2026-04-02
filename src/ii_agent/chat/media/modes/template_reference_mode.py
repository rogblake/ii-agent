"""Template reference mode strategy for media generation."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import MediaPreferences
from ii_agent.content.media.repository import MediaTemplateRepository
from ii_agent.content.media.service import MediaTemplateService
from ii_agent.core.config.settings import get_settings
from ii_agent.core.storage.client import get_storage
from .base import BaseModeStrategy

logger = logging.getLogger(__name__)


class TemplateReferenceModeStrategy(BaseModeStrategy):
    """
    Template reference mode for template-driven generation.

    - Keeps conversation context by default
    - Adds guidance to use the template image as a style reference
    - Emphasizes originality (do not copy template content)
    """

    def __init__(self, *, clear_context: bool = False) -> None:
        self._clear_context = clear_context
        self._template_preview_url: str | None = None
        self._template_name: str | None = None

    def should_clear_context(self) -> bool:
        """Template reference mode keeps context unless explicitly set."""
        return self._clear_context

    async def _ensure_template_loaded(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
    ) -> None:
        """Fetch template preview URL for reference-based generation."""
        if not media_preferences.template_id:
            return

        if self._template_preview_url:
            return

        try:
            template = await MediaTemplateService(
                config=get_settings(),
                repo=MediaTemplateRepository(),
                media_storage=get_storage(),
            ).get_media_template_by_id(db_session, media_preferences.template_id)
            if template:
                self._template_preview_url = template.preview
                self._template_name = template.name
        except Exception as e:
            logger.warning(
                f"[TEMPLATE_REFERENCE] Failed to load template {media_preferences.template_id}: {e}"
            )

    async def get_template_preview_url(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
    ) -> str | None:
        await self._ensure_template_loaded(
            db_session=db_session,
            session_id=session_id,
            media_preferences=media_preferences,
        )
        return self._template_preview_url

    async def build_prompt_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build prompt context for template reference mode."""
        if not media_preferences.template_id:
            return ""

        if not self._template_preview_url:
            await self._ensure_template_loaded(
                db_session=db_session,
                session_id=session_id,
                media_preferences=media_preferences,
            )

        if not self._template_preview_url:
            return ""

        template_name = f"{self._template_name}" if self._template_name else "the selected template"
        return (
            "\n\n[Template Style Reference]\n"
            f"A style reference image from {template_name} is attached in this message. "
            "Use it ONLY to match overall style: layout rhythm, typography feel, color palette, "
            "graphic treatment, and texture. "
            "Do NOT copy any specific text, logos, characters, or exact layout elements from the reference. "
            "Create an original poster that follows the style but uses new content based on the user's request."
        )

    def get_mode_name(self) -> str:
        """Return mode name for logging."""
        return "template_reference"
