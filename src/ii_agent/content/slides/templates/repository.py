"""Repository layer for slide templates subdomain - data access only."""

from typing import Optional, Dict, Any, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.content.slides.models import SlideTemplate
from ii_agent.content.slides.templates.schemas import SlideTemplateInfo


class SlideTemplateRepository:
    """Data access layer for slide templates."""

    async def get_by_id(self, db: AsyncSession, template_id: str) -> Optional[Dict[str, Any]]:
        """Get slide template by ID."""
        result = await db.execute(
            select(SlideTemplate).where(SlideTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()

        if template:
            return {
                "id": template.id,
                "slide_template_name": template.slide_template_name,
                "slide_content": template.slide_content,
                "slide_template_images": template.slide_template_images,
            }

        return None

    async def get_full_by_id(self, db: AsyncSession, template_id: str) -> Optional[SlideTemplateInfo]:
        """Get full slide template by ID including timestamps."""
        result = await db.execute(
            select(SlideTemplate).where(SlideTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()

        if template:
            return SlideTemplateInfo.model_validate(template)

        return None

    async def list_paginated(
        self, db: AsyncSession, page: int = 1, page_size: int = 20, search: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get paginated list of slide templates."""
        offset = (page - 1) * page_size

        # Build base query and count query
        base_query = select(SlideTemplate)
        count_query = select(func.count()).select_from(SlideTemplate)

        if search:
            search_filter = SlideTemplate.slide_template_name.ilike(f"%{search}%")
            base_query = base_query.where(search_filter)
            count_query = count_query.where(search_filter)

        # Execute paginated query
        query = base_query.order_by(SlideTemplate.created_at.desc()).limit(page_size).offset(offset)
        result = await db.execute(query)
        templates_rows = result.scalars().all()

        # Execute count query
        count_result = await db.execute(count_query)
        total_count = count_result.scalar()

        templates = [
            {
                "id": t.id,
                "slide_template_name": t.slide_template_name,
                "slide_template_images": t.slide_template_images,
            }
            for t in templates_rows
        ]

        total_pages = (total_count + page_size - 1) // page_size if total_count else 0

        return {
            "templates": templates,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def create(
        self,
        db: AsyncSession,
        *,
        template_name: str,
        content: str,
        images: Optional[List[str]] = None,
    ) -> SlideTemplateInfo:
        """Create a new slide template."""
        template = SlideTemplate(
            slide_template_name=template_name,
            slide_content=content,
            slide_template_images=images,
        )
        db.add(template)
        await db.flush()
        await db.refresh(template)

        return SlideTemplateInfo.model_validate(template)
