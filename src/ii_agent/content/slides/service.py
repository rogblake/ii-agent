"""Service layer for slides domain - business logic only."""

from __future__ import annotations

import logging
import base64
from collections import defaultdict
from typing import Optional, AsyncGenerator, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.core.config.settings import Settings
from ii_agent.content.slides.models import SlideContent
from ii_agent.content.slides.repository import SlideContentRepository
from ii_agent.sessions.repository import SessionRepository
from ii_agent.content.slides.schemas import (
    SlideWriteRequest,
    SlideWriteResponse,
    SlideContentInfo,
    PresentationInfo,
    PresentationListResponse,
)
from ii_agent.content.slides.pdf_service import (
    convert_slides_to_pdf,
    convert_slides_to_pdf_with_progress,
)

logger = logging.getLogger(__name__)


def _to_slide_content_info(slide: SlideContent) -> SlideContentInfo:
    """Convert database model to Pydantic model."""
    slide_content = slide.slide_content if slide.slide_content else ""

    return SlideContentInfo(
        id=slide.id,
        session_id=slide.session_id,
        presentation_name=slide.presentation_name,
        slide_number=slide.slide_number,
        slide_title=slide.slide_title or "",
        slide_content=slide_content,
        metadata=slide.slide_metadata or {},
        created_at=slide.created_at,
        updated_at=slide.updated_at,
    )


class SlideService:
    """Service for managing slides - business logic layer."""

    def __init__(
        self,
        *,
        slide_repo: SlideContentRepository,
        session_repo: SessionRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._slide_repo = slide_repo
        self._session_repo = session_repo

    async def execute_slide_write(
        self,
        db: AsyncSession,
        *,
        write_request: SlideWriteRequest,
        session_id: str,
        user_id: str,
    ) -> SlideWriteResponse:
        """Execute slide write by saving directly to database."""
        try:
            if not await self._session_repo.get_by_id_and_user(db, session_id, user_id):
                return SlideWriteResponse(
                    success=False,
                    presentation_name=write_request.presentation_name,
                    slide_number=write_request.slide_number,
                    error="Session not found or access denied",
                    error_code="SESSION_ACCESS_DENIED",
                )

            await self._slide_repo.upsert_slide(
                db,
                session_id=session_id,
                presentation_name=write_request.presentation_name,
                slide_number=write_request.slide_number,
                slide_title=write_request.title,
                slide_content=write_request.content,
                tool_name="SlideWrite",
            )

            return SlideWriteResponse(
                success=True,
                presentation_name=write_request.presentation_name,
                slide_number=write_request.slide_number,
            )

        except Exception as e:
            logger.error(f"Slide write request failed: {e}")
            return SlideWriteResponse(
                success=False,
                presentation_name=write_request.presentation_name,
                slide_number=write_request.slide_number,
                error=str(e),
                error_code="INTERNAL_ERROR",
            )

    async def persist_tool_slide_result(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: str,
        slide_number: int,
        slide_title: str | None,
        slide_content: str,
        tool_name: str,
    ) -> str:
        """Persist slide HTML emitted by agent tools."""
        existing_slide = await self._slide_repo.get_by_session_and_presentation_and_number(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
        )

        resolved_title = (
            slide_title or getattr(existing_slide, "slide_title", None) or f"Slide {slide_number}"
        )

        return await self._slide_repo.upsert_slide(
            db,
            session_id=session_id,
            presentation_name=presentation_name,
            slide_number=slide_number,
            slide_title=resolved_title,
            slide_content=slide_content,
            tool_name=tool_name,
        )

    async def get_session_presentations(
        self, db: AsyncSession, *, session_id: str, user_id: str
    ) -> PresentationListResponse:
        """Get list of presentations with all slide content in session."""
        try:
            if not await self._session_repo.get_by_id_and_user(db, session_id, user_id):
                return PresentationListResponse(session_id=session_id, presentations=[], total=0)

            return await self._build_presentation_list(db, session_id)

        except Exception as e:
            logger.error(f"Failed to get session presentations: {e}")
            return PresentationListResponse(session_id=session_id, presentations=[], total=0)

    async def get_public_session_presentations(
        self, db: AsyncSession, *, session_id: str
    ) -> PresentationListResponse:
        """Get list of presentations from a public session (no auth required)."""
        try:
            if not await self._session_repo.get_public_by_id(db, session_id):
                return PresentationListResponse(session_id=session_id, presentations=[], total=0)

            return await self._build_presentation_list(db, session_id)

        except Exception as e:
            logger.error(f"Failed to get public session presentations: {e}")
            return PresentationListResponse(session_id=session_id, presentations=[], total=0)

    async def download_session_slides_as_pdf(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
        presentation_name: Optional[str] = None,
    ) -> Optional[bytes]:
        """Download slides from session as PDF for authenticated users."""
        try:
            if not await self._session_repo.get_by_id_and_user(db, session_id, user_id):
                logger.error(f"Session {session_id} not found or access denied for user {user_id}")
                return None

            return await self._slides_to_pdf(db, session_id, presentation_name)

        except Exception as e:
            logger.error(f"Failed to download slides as PDF: {e}")
            return None

    async def download_public_session_slides_as_pdf(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: Optional[str] = None,
    ) -> Optional[bytes]:
        """Download slides from public session as PDF."""
        try:
            if not await self._session_repo.get_public_by_id(db, session_id):
                logger.error(f"Session {session_id} not found or not public")
                return None

            return await self._slides_to_pdf(db, session_id, presentation_name)

        except Exception as e:
            logger.error(f"Failed to download public slides as PDF: {e}")
            return None

    async def download_session_slides_as_pdf_with_progress(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
        presentation_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download slides from session as PDF with progress updates."""
        try:
            if not await self._session_repo.get_by_id_and_user(db, session_id, user_id):
                yield {
                    "type": "error",
                    "message": f"Session {session_id} not found or access denied for user {user_id}",
                }
                return

            async for data in self._slides_to_pdf_with_progress(db, session_id, presentation_name):
                yield data

        except Exception as e:
            logger.error(f"Failed to download slides as PDF with progress: {e}")
            yield {"type": "error", "message": str(e)}

    async def download_public_session_slides_as_pdf_with_progress(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        presentation_name: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download slides from public session as PDF with progress updates."""
        try:
            if not await self._session_repo.get_public_by_id(db, session_id):
                yield {
                    "type": "error",
                    "message": f"Session {session_id} not found or not public",
                }
                return

            async for data in self._slides_to_pdf_with_progress(db, session_id, presentation_name):
                yield data

        except Exception as e:
            logger.error(f"Failed to download public slides as PDF with progress: {e}")
            yield {"type": "error", "message": str(e)}

    # ==================== Private Helpers ====================

    async def _build_presentation_list(
        self, db: AsyncSession, session_id: str
    ) -> PresentationListResponse:
        """Build full presentation list with slides for a session."""
        summary_rows = await self._slide_repo.get_presentations_summary(db, session_id)

        # Single query for all slides, then group by presentation name in Python
        all_slides = await self._slide_repo.get_slides_by_session(db, session_id)
        slides_by_presentation: dict[str, list[SlideContentInfo]] = defaultdict(list)
        for slide in all_slides:
            slides_by_presentation[slide.presentation_name].append(_to_slide_content_info(slide))

        presentations = []
        for row in summary_rows:
            presentations.append(
                PresentationInfo(
                    name=row.presentation_name,
                    slide_count=row.slide_count,
                    last_updated=row.last_updated,
                    slides=slides_by_presentation.get(row.presentation_name, []),
                )
            )

        return PresentationListResponse(
            session_id=session_id,
            presentations=presentations,
            total=len(presentations),
        )

    async def _slides_to_pdf(
        self, db: AsyncSession, session_id: str, presentation_name: Optional[str]
    ) -> Optional[bytes]:
        """Fetch slides and convert to PDF."""
        slides = await self._slide_repo.get_slides_by_session(db, session_id, presentation_name)
        if not slides:
            logger.warning(f"No slides found for session {session_id}")
            return None

        slide_infos = [_to_slide_content_info(slide) for slide in slides]
        return await convert_slides_to_pdf(slide_infos)

    async def _slides_to_pdf_with_progress(
        self, db: AsyncSession, session_id: str, presentation_name: Optional[str]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch slides and convert to PDF with progress updates."""
        slides = await self._slide_repo.get_slides_by_session(db, session_id, presentation_name)
        if not slides:
            yield {
                "type": "error",
                "message": f"No slides found for session {session_id}",
            }
            return

        slide_infos = [_to_slide_content_info(slide) for slide in slides]

        filename = f"slides_{session_id}"
        if presentation_name:
            filename = f"{presentation_name}_{session_id}"
        filename += ".pdf"

        async for progress_data in convert_slides_to_pdf_with_progress(slide_infos):
            if progress_data["type"] == "complete":
                pdf_base64 = base64.b64encode(progress_data["pdf_bytes"]).decode("utf-8")
                yield {
                    "type": "complete",
                    "filename": filename,
                    "pdf_base64": pdf_base64,
                    "total_pages": progress_data["total_pages"],
                }
            else:
                yield progress_data


# Backward-compatible module-level function used by slide_event_handler
async def _save_slide_to_db(
    *,
    db_session,
    session_id: str,
    presentation_name: str,
    slide_number: int,
    slide_title: str,
    slide_content: str,
    tool_name: str,
) -> str:
    """Save slide content to database (backward-compatible wrapper).

    Used by slide_event_handler which creates its own db session.
    """
    repo = SlideContentRepository()
    return await repo.upsert_slide(
        db_session,
        session_id=session_id,
        presentation_name=presentation_name,
        slide_number=slide_number,
        slide_title=slide_title,
        slide_content=slide_content,
        tool_name=tool_name,
    )
