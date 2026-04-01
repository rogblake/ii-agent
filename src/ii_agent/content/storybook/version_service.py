"""Storybook versioning service for page text updates and image regeneration."""

from __future__ import annotations

import uuid
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.content.storybook.models import Storybook, StorybookPage
from ii_agent.content.storybook.schemas import StorybookDetail
from ii_agent.content.storybook.html_generator import generate_storybook_page_html
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.storybook.export_utils import find_page_by_number
from ii_agent.core.config.settings import Settings

if TYPE_CHECKING:
    from ii_agent.content.storybook.service import StorybookService

logger = logging.getLogger(__name__)


class StorybookVersionService:
    """Service for storybook versioning: text updates, image regeneration, version creation."""

    def __init__(
        self,
        *,
        repo: StorybookRepository,
        storybook_service: StorybookService,
        config: Settings,
    ) -> None:
        self._repo = repo
        self._storybook_service = storybook_service
        self._config = config

    async def create_storybook_version(
        self,
        db: AsyncSession,
        *,
        source_storybook_id: str,
        edited_page_number: int,
        page_updates: Dict[str, Any],
    ) -> Optional[StorybookDetail]:
        """Create a new version of a storybook with an updated page."""
        return await self.create_storybook_version_multi_page(
            db,
            source_storybook_id=source_storybook_id,
            page_updates={edited_page_number: page_updates},
        )

    async def create_storybook_version_multi_page(
        self,
        db: AsyncSession,
        *,
        source_storybook_id: str,
        page_updates: Dict[int, Dict[str, Any]],
    ) -> Optional[StorybookDetail]:
        """Create a new version with updates applied to one or more pages."""
        source = await self._repo.get_by_id(db, source_storybook_id)
        if not source:
            return None
        if not page_updates:
            return None

        new_storybook = Storybook(
            id=str(uuid.uuid4()),
            session_id=source.session_id,
            name=source.name,
            version=(source.version or 1) + 1,
            style_json=source.style_json,
            aspect_ratio=source.aspect_ratio,
            resolution=source.resolution,
            root_storybook_id=source.root_storybook_id or source.id,
            parent_storybook_id=source.id,
        )
        new_storybook = await self._repo.save(db, new_storybook)

        new_pages = []
        for page in source.pages or []:
            page_metadata = dict(page.page_metadata or {})
            image_url = page.image_url
            html_content = page.html_content
            text_content = page.text_content
            audio_link = page.audio_link

            updates = page_updates.get(page.page_number) or {}
            if updates:
                image_url = updates.get("image_url", image_url)
                html_content = updates.get("html_content", html_content)
                text_content = updates.get("text_content", text_content)
                audio_link = updates.get("audio_link", audio_link)
                if "image_prompt" in updates:
                    page_metadata["image_prompt"] = updates["image_prompt"]

            new_pages.append(StorybookPage(
                id=str(uuid.uuid4()),
                page_number=page.page_number,
                image_url=image_url,
                html_content=html_content,
                text_content=text_content,
                audio_link=audio_link,
                page_metadata=page_metadata,
            ))

        if new_pages:
            await self._repo.create_pages_batch(db, new_pages, storybook_id=new_storybook.id)

        return await self._storybook_service.get_storybook_detail(db, new_storybook.id, include_pages=True)

    async def update_page_text(
        self,
        db: AsyncSession,
        storybook_id: str,
        page_number: int,
        new_text: str,
    ) -> Optional[StorybookDetail]:
        """Update page text and create a new storybook version (auto-versioning)."""
        source_storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not source_storybook:
            return None

        source_page = find_page_by_number(source_storybook.pages, page_number)
        if not source_page:
            logger.error(f"Page {page_number} not found in storybook {storybook_id}")
            return None

        new_html = generate_storybook_page_html(
            image_url=source_page.image_url or "",
            text_content=new_text,
            text_position=source_page.text_position,
            text_percentage=source_page.text_percentage,
            aspect_ratio=source_storybook.aspect_ratio,
            resolution=source_storybook.resolution,
            page_number=page_number,
        )

        return await self.create_storybook_version(
            db,
            source_storybook_id=storybook_id,
            edited_page_number=page_number,
            page_updates={"text_content": new_text, "html_content": new_html},
        )

    async def regenerate_page_image(
        self,
        db: AsyncSession,
        storybook_id: str,
        page_number: int,
        new_image_prompt: str,
        generate_image_func,
        user_api_key: str,
        session_id: str,
    ) -> Optional[StorybookDetail]:
        """Regenerate page image and create a new storybook version (auto-versioning)."""
        source_storybook = await self._storybook_service.get_storybook_detail(
            db, storybook_id, include_pages=True
        )
        if not source_storybook:
            return None

        source_page = find_page_by_number(source_storybook.pages, page_number)
        if not source_page:
            logger.error(f"Page {page_number} not found in storybook {storybook_id}")
            return None

        new_image_url = await generate_image_func(
            prompt=new_image_prompt,
            user_api_key=user_api_key,
            session_id=session_id,
            aspect_ratio=source_storybook.aspect_ratio,
            resolution=source_storybook.resolution,
        )

        new_html = generate_storybook_page_html(
            image_url=new_image_url,
            text_content=source_page.text_content or "",
            text_position=source_page.text_position,
            text_percentage=source_page.text_percentage,
            aspect_ratio=source_storybook.aspect_ratio,
            resolution=source_storybook.resolution,
            page_number=page_number,
        )

        return await self.create_storybook_version(
            db,
            source_storybook_id=storybook_id,
            edited_page_number=page_number,
            page_updates={
                "image_url": new_image_url,
                "image_prompt": new_image_prompt,
                "html_content": new_html,
            },
        )
