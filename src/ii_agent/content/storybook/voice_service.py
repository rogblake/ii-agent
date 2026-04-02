"""Storybook voice-over generation service."""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.service import CreditService
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.storybook.schemas import (
    StorybookDetail,
    StorybookVoiceOverResponse,
)
from ii_agent.content.storybook.service import _storybook_to_detail
from ii_agent.core.config.settings import Settings

if TYPE_CHECKING:
    from ii_agent.content.storybook.service import StorybookService

logger = logging.getLogger(__name__)


# ==================== Voice Helpers (module-level) ====================

_voice_service = None


def _get_voice_service():
    """Lazily initialize voice generation service."""
    global _voice_service
    if _voice_service is not None:
        return _voice_service

    try:
        from ii_agent_tools.client.tool_client_config import ToolClientSettings
        from ii_agent_tools.integrations.voice_generation.service import (
            VoiceGenerationService,
        )
    except Exception as exc:
        logger.warning("[STORYBOOK] Voice generation imports unavailable: %s", exc)
        _voice_service = None
        return None

    try:
        tool_settings = ToolClientSettings()
        _voice_service = VoiceGenerationService(tool_settings.voice_generate_config)
    except Exception as exc:
        logger.warning("[STORYBOOK] Failed to initialize voice generation: %s", exc)
        _voice_service = None

    return _voice_service


def _extract_plain_text(html_content: str) -> str:
    """Extract plain text from HTML content."""
    if not html_content:
        return ""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    nodes = soup.select('[data-editable="text"]')
    if nodes:
        text = " ".join(node.get_text(" ", strip=True) for node in nodes)
    else:
        text = soup.get_text(" ", strip=True)
    return text.strip()


def _resolve_language_code(
    language_code: Optional[str],
    style_json: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Resolve language code from explicit param or style_json."""
    if language_code:
        return language_code
    if not isinstance(style_json, dict):
        return None
    for key in ("language_code", "languageCode", "language"):
        value = style_json.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _generate_voice_audio(
    voice_service: Any,
    *,
    text: str,
    session_id: str,
    language_code: Optional[str] = None,
) -> tuple[Optional[str], float]:
    """Generate voice audio for text.

    Returns (audio_url, cost_usd). Returns (None, 0.0) on failure.
    """
    if not text or not text.strip():
        return None, 0.0
    if not voice_service:
        return None, 0.0
    try:
        voice_kwargs: Dict[str, Any] = {
            "text": text.strip(),
            "session_id": session_id,
        }
        if language_code:
            voice_kwargs["language_code"] = language_code
        result = await voice_service.generate_voice(**voice_kwargs)
        return result.url, getattr(result, "cost", 0.0) or 0.0
    except Exception as exc:
        logger.warning("[STORYBOOK] Voice generation failed: %s", exc)
        return None, 0.0


# ==================== Service ====================


class StorybookVoiceService:
    """Service for storybook voice-over generation and credit deduction."""

    def __init__(
        self,
        *,
        repo: StorybookRepository,
        storybook_service: StorybookService,
        config: Settings,
        credit_service: CreditService,
    ) -> None:
        self._repo = repo
        self._storybook_service = storybook_service
        self._config = config
        self._credit_service = credit_service

    async def generate_voiceover(
        self,
        db: AsyncSession,
        storybook_id: str,
        user_id: str,
        language_code: Optional[str] = None,
        force: bool = False,
    ) -> tuple[Optional[StorybookDetail], bool, float]:
        """Generate voice-over audio for a storybook and update page audio links.

        Returns:
            Tuple of (StorybookDetail, generated_any, total_voice_cost_usd).
        """
        storybook = await self._repo.get_by_id(db, storybook_id)
        if not storybook:
            return (None, False, 0.0)

        voice_service = _get_voice_service()
        if not voice_service:
            return (None, False, 0.0)

        pages = storybook.pages or []
        if not pages:
            return (_storybook_to_detail(storybook), False, 0.0)

        has_separate_text_pages = any(
            (p.page_metadata or {}).get("is_text_only_page") for p in pages
        )

        resolved_language = _resolve_language_code(
            language_code, storybook.style_json
        )
        session_id = storybook.session_id or ""
        if not session_id:
            return (None, False, 0.0)

        generated_any = False
        total_voice_cost_usd = 0.0

        for page in pages:
            if page.audio_link and not force:
                continue

            metadata = page.page_metadata or {}
            if has_separate_text_pages:
                is_cover_page = page.page_number == 1
                if not is_cover_page and not metadata.get("is_text_only_page"):
                    continue

            text = (page.text_content or "").strip()
            if not text:
                text = _extract_plain_text(page.html_content or "")

            if not text:
                if force and page.audio_link:
                    await self._repo.update_page(db, page.id, audio_link=None)
                continue

            audio_link, voice_cost_usd = await _generate_voice_audio(
                voice_service,
                text=text,
                session_id=session_id,
                language_code=resolved_language,
            )
            if audio_link:
                await self._repo.update_page(db, page.id, audio_link=audio_link)
                generated_any = True
                total_voice_cost_usd += voice_cost_usd

        # Refresh to get updated page data
        refreshed = await self._repo.get_by_id(db, storybook_id)
        detail = _storybook_to_detail(refreshed) if refreshed else None
        return (detail, generated_any, total_voice_cost_usd)

    async def generate_voiceover_and_deduct_credits(
        self,
        db: AsyncSession,
        storybook_id: str,
        user_id: str,
        session_id: str,
        language_code: Optional[str] = None,
        force: bool = False,
    ) -> StorybookVoiceOverResponse:
        """Generate voice-over and deduct credits in one service call."""
        # Credit calculation constant: 100 credits = $1.5 USD
        USD_TO_CREDITS_MULTIPLIER = 100 / 1.5  # ~66.67

        updated_storybook, generated_any, total_voice_cost_usd = (
            await self.generate_voiceover(
                db,
                storybook_id=storybook_id,
                user_id=user_id,
                language_code=language_code,
                force=force,
            )
        )

        if not updated_storybook:
            return StorybookVoiceOverResponse(
                success=False,
                error="Voice generation is unavailable right now.",
            )

        if not generated_any:
            if force and updated_storybook:
                pages = updated_storybook.pages or []
                has_audio = any(page.audio_link for page in pages)
                if has_audio:
                    return StorybookVoiceOverResponse(
                        success=True, storybook=updated_storybook
                    )
            return StorybookVoiceOverResponse(
                success=False,
                storybook=updated_storybook,
                error="No voice audio was generated for this storybook.",
            )

        if total_voice_cost_usd > 0:
            credits_to_deduct = total_voice_cost_usd * USD_TO_CREDITS_MULTIPLIER
            deduct_success = await self._credit_service.deduct(
                db, user_id, credits_to_deduct
            )
            if deduct_success:
                await self._credit_service.accumulate_session_usage(
                    db, session_id, -credits_to_deduct
                )
                await db.commit()
                logger.info(
                    f"[Storybook Voice] Deducted {credits_to_deduct:.4f} credits "
                    f"(voice cost: ${total_voice_cost_usd:.4f}) for storybook {storybook_id}"
                )
            else:
                logger.warning(
                    f"[Storybook Voice] Failed to deduct credits for user {user_id}"
                )

        return StorybookVoiceOverResponse(success=True, storybook=updated_storybook)

    def get_generation_status(self, storybook: StorybookDetail) -> Optional[str]:
        """Extract generation status from storybook style_json."""
        if isinstance(storybook.style_json, dict):
            generation = storybook.style_json.get("generation")
            if isinstance(generation, dict):
                return generation.get("status")
        return None

    async def cancel_generation(
        self,
        db: AsyncSession,
        storybook_id: str,
    ) -> bool:
        """Cancel storybook generation via Redis and update status."""
        from ii_agent.core.redis.cancel import cancel_run

        await cancel_run(storybook_id)

        await self._repo.update_generation_status(
            db,
            storybook_id,
            status="failed",
            generating_pages=[],
            error_message="storybook_cancelled",
        )
        return True
