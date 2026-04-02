"""Generic base repository with common CRUD operations.

All domain repositories can inherit from ``BaseRepository`` to avoid
repeating the standard ``get_by_id``, ``create``, and ``update``
boilerplate.  Domain-specific query methods are still defined on each
subclass.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Typed base repository providing common data-access patterns.

    Subclasses must set ``model`` as a class variable::

        class FileRepository(BaseRepository[FileUpload]):
            model = FileUpload
    """

    model: type[T]

    async def get_by_id(self, db: AsyncSession, entity_id: Any) -> T | None:
        """Fetch a single entity by primary key."""
        result = await db.execute(
            select(self.model).where(self.model.id == entity_id)
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, entity: T) -> T:
        """Add a new entity, flush, and refresh from DB."""
        db.add(entity)
        await db.flush()
        await db.refresh(entity)
        return entity

    async def update(self, db: AsyncSession, entity: T) -> T:
        """Flush pending changes on a tracked entity and refresh."""
        await db.flush()
        await db.refresh(entity)
        return entity
