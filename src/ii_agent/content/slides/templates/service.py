"""Service layer for slide templates subdomain - business logic only."""

from __future__ import annotations

from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.content.slides.templates.repository import SlideTemplateRepository
from ii_agent.content.slides.templates.schemas import SlideTemplateCreate, SlideTemplateInfo


class SlideTemplateService:
    """Service for managing slide templates - business logic layer."""

    def __init__(self, *, template_repo: SlideTemplateRepository, config: Settings) -> None:
        self._config = config
        self._template_repo = template_repo

    async def get_slide_template_by_id(
        self, db: AsyncSession, template_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get slide template by ID."""
        return await self._template_repo.get_by_id(db, template_id)

    async def get_slide_template_content_by_id(
        self, db: AsyncSession, template_id: str
    ) -> Optional[Any]:
        """Get only the slide content for a template by ID."""
        template = await self._template_repo.get_by_id(db, template_id)
        return template["slide_content"] if template else None

    async def get_slide_template_full_by_id(
        self, db: AsyncSession, template_id: str
    ) -> Optional[SlideTemplateInfo]:
        """Get full slide template by ID including timestamps."""
        return await self._template_repo.get_full_by_id(db, template_id)

    async def list_slide_templates(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated list of slide templates."""
        return await self._template_repo.list_paginated(db, page, page_size, search)

    async def create_slide_template(
        self, db: AsyncSession, template: SlideTemplateCreate
    ) -> SlideTemplateInfo:
        """Create a new slide template."""
        return await self._template_repo.create(
            db,
            template_name=template.slide_template_name,
            content=template.slide_content,
            images=template.slide_template_images,
        )


# Backward-compatible module-level functions for non-DI callers
async def get_slide_template_by_id(
    db: AsyncSession, template_id: str
) -> Optional[Dict[str, Any]]:
    """Get slide template by ID (backward-compatible wrapper)."""
    repo = SlideTemplateRepository()
    return await repo.get_by_id(db, template_id)


async def get_slide_template_content_by_id(
    db: AsyncSession, template_id: str
) -> Optional[Any]:
    """Get only the slide content for a template by ID (backward-compatible wrapper)."""
    template = await get_slide_template_by_id(db, template_id)
    return template["slide_content"] if template else None


async def list_slide_templates(
    db: AsyncSession, page: int = 1, page_size: int = 20, search: Optional[str] = None
) -> Dict[str, Any]:
    """Get paginated list of slide templates (backward-compatible wrapper)."""
    repo = SlideTemplateRepository()
    return await repo.list_paginated(db, page, page_size, search)
