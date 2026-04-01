"""Repository layer for storybook domain - data access only."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ii_agent.core.db.base import BaseRepository
from ii_agent.content.storybook.models import Storybook, StorybookPage, StorybookPageLink


class StorybookRepository(BaseRepository[Storybook]):
    """Data access layer for Storybook and StorybookPage models.

    Inherits from BaseRepository: get_by_id (basic), save, update.
    Overrides get_by_id to eager-load pages.
    """

    model = Storybook

    async def get_by_id(
        self, db: AsyncSession, storybook_id: Any
    ) -> Optional[Storybook]:
        """Get a storybook by ID, always eager-loading pages."""
        query = select(Storybook).where(Storybook.id == storybook_id).options(
            selectinload(Storybook.pages)
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_session_id(
        self, db: AsyncSession, session_id: str
    ) -> List[Storybook]:
        """Get all storybooks for a session, always eager-loading pages."""
        query = select(Storybook).where(Storybook.session_id == session_id).options(
            selectinload(Storybook.pages)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create_page(
        self, db: AsyncSession, page: StorybookPage, storybook_id: str
    ) -> StorybookPage:
        """Persist a new storybook page and link it to a storybook."""
        db.add(page)
        await db.flush()

        # Create the association link
        link = StorybookPageLink(storybook_id=storybook_id, page_id=page.id)
        db.add(link)
        await db.flush()

        await db.refresh(page)
        return page

    async def create_pages_batch(
        self, db: AsyncSession, pages: list[StorybookPage], storybook_id: str
    ) -> list[StorybookPage]:
        """Persist multiple pages and link them to a storybook in two flushes."""
        for page in pages:
            db.add(page)
        await db.flush()

        links = [StorybookPageLink(storybook_id=storybook_id, page_id=page.id) for page in pages]
        for link in links:
            db.add(link)
        await db.flush()

        for page in pages:
            await db.refresh(page)
        return pages

    async def get_page_by_number(
        self, db: AsyncSession, storybook_id: str, page_number: int
    ) -> Optional[StorybookPage]:
        """Get a storybook page by storybook_id and page_number."""
        query = (
            select(StorybookPage)
            .join(StorybookPageLink, StorybookPageLink.page_id == StorybookPage.id)
            .where(
                StorybookPageLink.storybook_id == storybook_id,
                StorybookPage.page_number == page_number,
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def update_page(
        self,
        db: AsyncSession,
        page_id: str,
        *,
        html_content: Optional[str] = None,
        image_url: Optional[str] = None,
        text_content: Optional[str] = None,
        audio_link: Optional[str] = None,
    ) -> Optional[StorybookPage]:
        """Update a storybook page's fields."""
        result = await db.execute(
            select(StorybookPage).where(StorybookPage.id == page_id)
        )
        page = result.scalar_one_or_none()
        if not page:
            return None

        if html_content is not None:
            page.html_content = html_content
        if image_url is not None:
            page.image_url = image_url
        if text_content is not None:
            page.text_content = text_content
        if audio_link is not None:
            page.audio_link = audio_link

        page.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(page)
        return page

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
        """Update storybook generation metadata stored in style_json.

        Uses FOR UPDATE row locking to prevent race conditions.
        """
        result = await db.execute(
            select(Storybook)
            .where(Storybook.id == storybook_id)
            .with_for_update()
        )
        storybook = result.scalar_one_or_none()
        if not storybook:
            return None

        style_json = dict(storybook.style_json or {})
        generation = dict(style_json.get("generation", {}))

        if status is not None:
            generation["status"] = status
        if total_pages is not None:
            generation["total_pages"] = total_pages
        if completed_pages is not None:
            generation["completed_pages"] = completed_pages
        if generating_pages is not None:
            generation["generating_pages"] = generating_pages
        if error_message is not None:
            generation["error_message"] = error_message
        if generation_meta:
            generation.update(generation_meta)
        generation["updated_at"] = datetime.now(timezone.utc).isoformat()

        style_json["generation"] = generation
        storybook.style_json = style_json
        storybook.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(storybook)
        return storybook

    async def get_version_family(self, db: AsyncSession, root_storybook_id: str) -> List[Storybook]:
        """Get all storybooks sharing the same root (for version history)."""
        query = (
            select(Storybook)
            .where(
                or_(
                    Storybook.id == root_storybook_id,
                    Storybook.root_storybook_id == root_storybook_id,
                )
            )
            .order_by(Storybook.version.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())
