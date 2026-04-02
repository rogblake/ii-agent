"""Storybook service layer for CRUD operations and business logic."""

from __future__ import annotations

import uuid
import logging
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.content.storybook.models import Storybook, StorybookPage
from ii_agent.content.storybook.schemas import (
    StorybookInfo,
    StorybookDetail,
    StorybookPageInfo,
    StorybookListResponse,
    StorybookGenerationResponse,
    StorybookProgressPage,
    StorybookProgressResponse,
    StorybookResultPage,
    StorybookResultResponse,
)
from ii_agent.core.config.settings import Settings
from ii_agent.content.storybook.html_generator import generate_storybook_page_html
from ii_agent.content.storybook.repository import StorybookRepository

logger = logging.getLogger(__name__)


# ==================== Serialization Helpers ====================


def _page_to_info(page: StorybookPage, storybook_id: str = "") -> StorybookPageInfo:
    """Convert a StorybookPage ORM model to a StorybookPageInfo schema."""
    metadata = page.page_metadata or {}
    return StorybookPageInfo(
        id=page.id,
        storybook_id=storybook_id,
        page_number=page.page_number,
        image_url=page.image_url,
        image_prompt=metadata.get("image_prompt"),
        text_content=page.text_content,
        audio_link=page.audio_link,
        text_position=metadata.get("text_position", "none"),
        text_percentage=metadata.get("text_percentage", 30),
        html_content=page.html_content,
        metadata=metadata,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def _storybook_to_info(storybook: Storybook) -> StorybookInfo:
    """Convert a Storybook ORM model to a StorybookInfo schema."""
    return StorybookInfo(
        id=storybook.id,
        session_id=storybook.session_id,
        name=storybook.name or "",
        version=storybook.version,
        style_json=storybook.style_json,
        aspect_ratio=storybook.aspect_ratio or "1:1",
        resolution=storybook.resolution or "1K",
        page_count=len(storybook.pages) if storybook.pages else 0,
        created_at=storybook.created_at,
        updated_at=storybook.updated_at,
    )


def _storybook_to_detail(storybook: Storybook) -> StorybookDetail:
    """Convert a Storybook ORM model (with pages loaded) to a StorybookDetail schema."""
    pages = [_page_to_info(p, storybook.id) for p in storybook.pages] if storybook.pages else []
    return StorybookDetail(
        id=storybook.id,
        session_id=storybook.session_id,
        name=storybook.name or "",
        version=storybook.version,
        style_json=storybook.style_json,
        aspect_ratio=storybook.aspect_ratio or "1:1",
        resolution=storybook.resolution or "1K",
        page_count=len(pages),
        created_at=storybook.created_at,
        updated_at=storybook.updated_at,
        pages=pages,
    )


def _db_page_to_display_page(db_page_number: int, separate_page_mode: bool) -> int:
    """Convert DB page number to display page number."""
    if db_page_number == 1:
        return 1
    if not separate_page_mode:
        return db_page_number
    return db_page_number // 2 + 1


# ==================== Service ====================


class StorybookService:
    """Service for storybook CRUD, queries, and generation response building."""

    def __init__(self, *, repo: StorybookRepository, config: Settings) -> None:
        self._config = config
        self._repo = repo

    # ---------- Low-level CRUD (return ORM models) ----------

    async def create_storybook(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        name: str,
        style_json: Optional[Dict[str, Any]] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        page_count: int = 0,
    ) -> Storybook:
        """Create a new storybook and return the ORM model."""
        storybook = Storybook(
            id=str(uuid.uuid4()),
            session_id=session_id,
            name=name,
            style_json=style_json,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        return await self._repo.save(db, storybook)

    async def create_storybook_page(
        self,
        db: AsyncSession,
        *,
        storybook_id: str,
        page_number: int,
        image_url: Optional[str] = None,
        image_prompt: Optional[str] = None,
        text_content: Optional[str] = None,
        text_position: str = "none",
        text_percentage: int = 30,
        html_content: Optional[str] = None,
        audio_link: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StorybookPage:
        """Create a new storybook page and return the ORM model."""
        page_metadata = metadata or {}
        page_metadata["image_prompt"] = image_prompt
        page_metadata["text_position"] = text_position
        page_metadata["text_percentage"] = text_percentage

        page = StorybookPage(
            id=str(uuid.uuid4()),
            page_number=page_number,
            image_url=image_url,
            html_content=html_content,
            text_content=text_content,
            audio_link=audio_link,
            page_metadata=page_metadata,
        )
        return await self._repo.create_page(db, page, storybook_id=storybook_id)

    async def update_generation_status(
        self,
        db: AsyncSession,
        storybook_id: str,
        *,
        status: Optional[str] = None,
        total_pages: Optional[int] = None,
        completed_pages: Optional[int] = None,
        generating_pages: Optional[List[int]] = None,
        error_message: Optional[str] = None,
        generation_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[Storybook]:
        """Update storybook generation metadata stored in style_json."""
        return await self._repo.update_generation_status(
            db,
            storybook_id,
            status=status,
            total_pages=total_pages,
            completed_pages=completed_pages,
            generating_pages=generating_pages,
            error_message=error_message,
            generation_meta=generation_meta,
        )

    # ---------- Query methods (return schema objects) ----------

    async def get_session_storybooks(
        self,
        db: AsyncSession,
        session_id: str,
        include_pages: bool = False,
    ) -> StorybookListResponse:
        """Get all storybooks for a session."""
        storybooks = await self._repo.get_by_session_id(db, session_id)
        infos = [_storybook_to_info(sb) for sb in storybooks]
        return StorybookListResponse(
            session_id=session_id,
            storybooks=infos,
            total=len(infos),
        )

    async def get_storybook_detail(
        self,
        db: AsyncSession,
        storybook_id: str,
        include_pages: bool = True,
    ) -> Optional[StorybookDetail]:
        """Get a storybook by ID with optional pages."""
        storybook = await self._repo.get_by_id(db, storybook_id)
        if not storybook:
            return None
        if include_pages:
            return _storybook_to_detail(storybook)
        info = _storybook_to_info(storybook)
        return StorybookDetail(**info.model_dump(), pages=[])

    # ---------- High-level business logic ----------

    async def create_storybook_with_info(
        self,
        db: AsyncSession,
        session_id: str,
        name: str,
        style_json: Optional[Dict[str, Any]] = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
    ) -> StorybookInfo:
        """Create a new storybook and return StorybookInfo."""
        storybook = await self.create_storybook(
            db,
            session_id=session_id,
            name=name,
            style_json=style_json,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        return _storybook_to_info(storybook)

    async def create_page_with_html(
        self,
        db: AsyncSession,
        storybook_id: str,
        page_number: int,
        image_url: str,
        image_prompt: str,
        text_content: str,
        text_position: str,
        text_percentage: int,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StorybookPageInfo:
        """Create a storybook page with auto-generated HTML."""
        html_content = generate_storybook_page_html(
            image_url=image_url,
            text_content=text_content,
            text_position=text_position,
            text_percentage=text_percentage,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            page_number=page_number,
        )
        page = await self.create_storybook_page(
            db,
            storybook_id=storybook_id,
            page_number=page_number,
            image_url=image_url,
            image_prompt=image_prompt,
            text_content=text_content,
            text_position=text_position,
            text_percentage=text_percentage,
            html_content=html_content,
            metadata=metadata,
        )
        return _page_to_info(page, storybook_id)

    def build_generation_response(
        self,
        storybook: StorybookDetail,
    ) -> StorybookGenerationResponse:
        """Build storybook generation progress or result response."""
        style_json = storybook.style_json or {}
        generation = style_json.get("generation") if isinstance(style_json, dict) else None
        generation = generation if isinstance(generation, dict) else {}

        separate_page_mode = (
            style_json.get("user_text_position") == "separate_page"
            if isinstance(style_json, dict)
            else False
        )

        image_pages: List[StorybookProgressPage] = []
        for page in storybook.pages or []:
            if not page.image_url:
                continue
            display_page = _db_page_to_display_page(page.page_number, separate_page_mode)
            image_pages.append(
                StorybookProgressPage(page_number=display_page, image_url=page.image_url)
            )

        completed_pages = generation.get("completed_pages")
        if isinstance(completed_pages, int):
            completed_pages = max(completed_pages, len(image_pages))
        else:
            completed_pages = len(image_pages)

        total_pages = generation.get("total_pages")
        if isinstance(total_pages, int):
            total_pages = max(total_pages, len(image_pages))
        else:
            total_pages = len(image_pages)

        status = generation.get("status")
        if status == "failed":
            status = "failed"
        else:
            is_complete = total_pages > 0 and completed_pages >= total_pages
            if status == "completed" or is_complete:
                status = "completed"
            else:
                status = "generating"

        generating_pages = generation.get("generating_pages")
        if not isinstance(generating_pages, list):
            generating_pages = []

        if status == "generating" and not generating_pages and total_pages:
            next_page = min(completed_pages + 1, total_pages)
            generating_pages = [next_page] if next_page > 0 else []

        current_page = min(completed_pages + 1, total_pages) if total_pages else completed_pages
        error_message = generation.get("error_message")

        if status == "completed":
            result_pages: List[StorybookResultPage] = []
            for page in storybook.pages or []:
                if not page.image_url:
                    continue
                display_page = _db_page_to_display_page(page.page_number, separate_page_mode)
                result_pages.append(
                    StorybookResultPage(page_number=display_page, image_url=page.image_url or "")
                )
            return StorybookResultResponse(
                storybook_id=storybook.id,
                storybook_name=storybook.name,
                version=storybook.version,
                pages=result_pages,
                aspect_ratio=storybook.aspect_ratio,
                resolution=storybook.resolution,
            )

        return StorybookProgressResponse(
            storybook_id=storybook.id,
            storybook_name=storybook.name,
            total_pages=total_pages,
            completed_pages=completed_pages,
            current_page=current_page,
            status=status,
            pages=image_pages,
            page=image_pages[-1] if image_pages else None,
            error_message=error_message if isinstance(error_message, str) else None,
            generating_pages=generating_pages,
        )
