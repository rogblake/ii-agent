"""Storybook voice-over generation service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.credits.service import CreditService
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.storybook.schemas import (
    StorybookDetail,
    StorybookVoiceOverResponse,
)
from ii_agent.content.storybook.service import _storybook_to_detail
from ii_agent.content.storybook.billing import (
    DEFAULT_STORYBOOK_VOICE_PAGE_RESERVE_USD,
    build_storybook_scope,
    check_and_deduct_storybook_credits,
)
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

        resolved_language = _resolve_language_code(language_code, storybook.style_json)
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
        idempotency_key: Optional[str] = None,
    ) -> StorybookVoiceOverResponse:
        """Generate voice-over and deduct credits in one service call."""
        if not await self._credit_service.has_sufficient_credits(db, user_id):
            raise InsufficientCreditsError(available_credits=0.0, required_credits=0.0)
        source_storybook = await self._repo.get_by_id(db, storybook_id)
        if not source_storybook:
            return StorybookVoiceOverResponse(
                success=False,
                error="Voice generation is unavailable right now.",
            )

        resolved_session_id = source_storybook.session_id or session_id
        if not resolved_session_id:
            return StorybookVoiceOverResponse(
                success=False,
                error="Voice generation is unavailable right now.",
            )

        estimated_page_count = self._estimate_billable_voice_pages(
            storybook=source_storybook,
            force=force,
        )

        if estimated_page_count <= 0:
            updated_storybook, generated_any, _ = await self.generate_voiceover(
                db,
                storybook_id=storybook_id,
                user_id=user_id,
                language_code=language_code,
                force=force,
            )
            return self._build_voiceover_response(
                updated_storybook=updated_storybook,
                generated_any=generated_any,
                force=force,
            )

        scope = build_storybook_scope(
            user_id=user_id,
            session_id=resolved_session_id,
        )

        # 1. Check credits up-front
        estimated_cost = DEFAULT_STORYBOOK_VOICE_PAGE_RESERVE_USD * estimated_page_count
        try:
            has_credits = await self._credit_service.has_sufficient_credits(
                db, user_id, float(estimated_cost)
            )
            if not has_credits:
                raise InsufficientCreditsError(
                    available_credits=0.0,
                    required_credits=float(estimated_cost),
                )
        except InsufficientCreditsError:
            logger.warning("[Storybook Voice] Insufficient credits for user %s", user_id)
            return StorybookVoiceOverResponse(
                success=False,
                storybook=None,
                error="Insufficient credits",
            )

        # 2. Execute the operation
        updated_storybook, generated_any, total_voice_cost_usd = await self.generate_voiceover(
            db,
            storybook_id=storybook_id,
            user_id=user_id,
            language_code=language_code,
            force=force,
        )

        # 3. Deduct actual cost
        if total_voice_cost_usd > 0:
            await check_and_deduct_storybook_credits(
                db,
                credit_service=self._credit_service,
                scope=scope,
                amount_usd=total_voice_cost_usd,
                tool_name="storybook_voiceover",
                metadata={
                    "storybook_id": storybook_id,
                    "voice_page_count_estimate": estimated_page_count,
                },
            )

        return self._build_voiceover_response(
            updated_storybook=updated_storybook,
            generated_any=generated_any,
            force=force,
        )

    def _estimate_billable_voice_pages(
        self,
        *,
        storybook,
        force: bool,
    ) -> int:
        """Estimate how many voice pages may need provider work."""
        pages = storybook.pages or []
        if not pages:
            return 0

        has_separate_text_pages = any(
            (getattr(page, "page_metadata", None) or getattr(page, "metadata", None) or {}).get(
                "is_text_only_page"
            )
            for page in pages
        )
        billable_pages = 0
        for page in pages:
            if page.audio_link and not force:
                continue

            metadata = getattr(page, "page_metadata", None) or getattr(page, "metadata", None) or {}
            if has_separate_text_pages:
                is_cover_page = page.page_number == 1
                if not is_cover_page and not metadata.get("is_text_only_page"):
                    continue

            text = (page.text_content or "").strip() or _extract_plain_text(page.html_content or "")
            if text:
                billable_pages += 1

        return billable_pages

    @staticmethod
    def _build_voiceover_response(
        *,
        updated_storybook: StorybookDetail | None,
        generated_any: bool,
        force: bool,
    ) -> StorybookVoiceOverResponse:
        """Preserve the existing storybook voice response behavior."""
        if not updated_storybook:
            return StorybookVoiceOverResponse(
                success=False,
                error="Voice generation is unavailable right now.",
            )

        if not generated_any:
            pages = updated_storybook.pages or []
            has_audio = any(page.audio_link for page in pages)
            if force and has_audio:
                return StorybookVoiceOverResponse(success=True, storybook=updated_storybook)
            return StorybookVoiceOverResponse(
                success=False,
                storybook=updated_storybook,
                error="No voice audio was generated for this storybook.",
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
