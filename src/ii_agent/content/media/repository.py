"""Repository layer for media domain - data access only."""

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.content.media.models import MediaTemplate


class MediaTemplateRepository(BaseRepository[MediaTemplate]):
    """Data access layer for the media_templates table.

    Inherits from BaseRepository: get_by_id, save, update.
    """

    model = MediaTemplate

    async def get_by_name(self, db: AsyncSession, name: str) -> Optional[MediaTemplate]:
        """Get a media template by its name."""
        result = await db.execute(select(MediaTemplate).where(MediaTemplate.name == name))
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        db: AsyncSession,
        *,
        page: int = 0,
        page_size: int = 20,
        search: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a paginated list of media templates.

        Returns:
            Dictionary with ``templates`` (list of MediaTemplate), ``total``,
            ``page``, ``page_size`` and ``total_pages``.
        """
        offset = page * page_size

        # Build base query with filters
        filters = []
        if search:
            filters.append(MediaTemplate.name.ilike(f"%{search}%"))
        if media_type:
            filters.append(MediaTemplate.type == media_type)

        # Data query
        query = (
            select(MediaTemplate)
            .where(*filters)
            .order_by(MediaTemplate.created_at)
            .limit(page_size)
            .offset(offset)
        )
        result = await db.execute(query)
        templates: List[MediaTemplate] = list(result.scalars().all())

        # Count query
        count_query = select(func.count()).select_from(MediaTemplate).where(*filters)
        count_result = await db.execute(count_query)
        total: int = count_result.scalar() or 0

        total_pages = (total + page_size - 1) // page_size if total else 0

        return {
            "templates": templates,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
