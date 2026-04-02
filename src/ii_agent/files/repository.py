"""Repository layer for files domain - data access only."""

from typing import List, Optional

from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.files.models import FileUpload


class FileRepository(BaseRepository[FileUpload]):
    """Data access layer for FileUpload model."""

    model = FileUpload

    async def get_by_id_and_user(
        self, db: AsyncSession, file_id: str, user_id: str
    ) -> Optional[FileUpload]:
        """Get a file upload by ID, validating user ownership."""
        result = await db.execute(
            select(FileUpload).where(
                and_(FileUpload.id == file_id, FileUpload.user_id == user_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_session_id(self, db: AsyncSession, session_id: str) -> List[FileUpload]:
        """Get all file uploads for a session."""
        result = await db.execute(
            select(FileUpload).where(FileUpload.session_id == session_id)
        )
        return result.scalars().all()

    async def get_by_session_and_id(
        self, db: AsyncSession, session_id: str, file_id: str
    ) -> Optional[FileUpload]:
        """Get a file upload by session ID and file ID."""
        result = await db.execute(
            select(FileUpload).where(
                and_(FileUpload.id == file_id, FileUpload.session_id == session_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_paths(
        self, db: AsyncSession, user_id: str, paths: List[str]
    ) -> List[FileUpload]:
        """Get file uploads by user ID and storage paths."""
        result = await db.execute(
            select(FileUpload).where(
                and_(
                    FileUpload.user_id == user_id,
                    FileUpload.storage_path.in_(paths),
                )
            )
        )
        return result.scalars().all()

    async def get_user_images(
        self, db: AsyncSession, user_id: str, *, limit: int, offset: int
    ) -> List[FileUpload]:
        """Get image file uploads for a user with pagination."""
        image_filter = or_(
            FileUpload.content_type.is_(None),
            FileUpload.content_type.ilike("image%"),
        )
        result = await db.execute(
            select(FileUpload)
            .where(and_(FileUpload.user_id == user_id, image_filter))
            .order_by(FileUpload.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def count_user_images(self, db: AsyncSession, user_id: str) -> int:
        """Count image file uploads for a user."""
        image_filter = or_(
            FileUpload.content_type.is_(None),
            FileUpload.content_type.ilike("image%"),
        )
        result = await db.execute(
            select(func.count())
            .select_from(FileUpload)
            .where(and_(FileUpload.user_id == user_id, image_filter))
        )
        return result.scalar_one()

    async def get_by_ids(self, db: AsyncSession, file_ids: list[str]) -> List[FileUpload]:
        """Get file uploads by a list of IDs."""
        if not file_ids:
            return []
        result = await db.execute(
            select(FileUpload).where(FileUpload.id.in_(file_ids))
        )
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        *,
        file_id: str,
        user_id: str,
        file_name: str,
        file_size: int,
        storage_path: str,
        content_type: str,
        session_id: Optional[str] = None,
    ) -> FileUpload:
        """Create a new file upload record."""
        db_file = FileUpload(
            id=file_id,
            user_id=user_id,
            file_name=file_name,
            file_size=file_size,
            storage_path=storage_path,
            content_type=content_type,
            session_id=session_id,
        )
        db.add(db_file)
        await db.flush()
        await db.refresh(db_file)
        return db_file

    async def update_session_id(self, db: AsyncSession, file_id: str, session_id: str) -> bool:
        """Update the session ID for a file upload."""
        file = await self.get_by_id(db, file_id)
        if file:
            file.session_id = session_id
            await db.flush()
            return True
        return False
