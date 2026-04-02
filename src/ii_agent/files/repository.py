"""Repository layer for files domain — unified data access."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.files.models import FileAsset, SessionAsset, UploadStatus


class FileRepository(BaseRepository[FileAsset]):
    """Unified data access for :class:`FileAsset` and :class:`SessionAsset`."""

    model = FileAsset

    # ------------------------------------------------------------------
    # FileAsset CRUD
    # ------------------------------------------------------------------

    async def create_asset(
        self,
        db: AsyncSession,
        *,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        file_name: str,
        storage_path: str,
        content_type: Optional[str] = None,
        file_size: Optional[int] = None,
        asset_type: str = "other",
        source: str = "user_upload",
        upload_status: str = UploadStatus.COMPLETE,
        is_public: bool = False,
        sandbox_path: Optional[str] = None,
        data: Optional[dict] = None,
    ) -> FileAsset:
        """Create a new file asset record."""
        asset = FileAsset(
            id=file_id,
            user_id=user_id,
            file_name=file_name,
            storage_path=storage_path,
            content_type=content_type,
            file_size=file_size,
            asset_type=asset_type,
            source=source,
            upload_status=upload_status,
            is_public=is_public,
            sandbox_path=sandbox_path,
            data=data or {},
        )
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        return asset

    async def get_by_id_and_user(
        self, db: AsyncSession, file_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[FileAsset]:
        """Get a file by ID, validating user ownership."""
        result = await db.execute(
            select(FileAsset).where(and_(FileAsset.id == file_id, FileAsset.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_paths(
        self, db: AsyncSession, user_id: uuid.UUID, paths: list[str]
    ) -> list[FileAsset]:
        """Get files by user ID and storage paths."""
        result = await db.execute(
            select(FileAsset).where(
                and_(
                    FileAsset.user_id == user_id,
                    FileAsset.storage_path.in_(paths),
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_ids(self, db: AsyncSession, file_ids: list[uuid.UUID]) -> list[FileAsset]:
        """Get files by a list of IDs."""
        if not file_ids:
            return []
        result = await db.execute(select(FileAsset).where(FileAsset.id.in_(file_ids)))
        return list(result.scalars().all())

    async def get_by_storage_path(self, db: AsyncSession, storage_path: str) -> FileAsset | None:
        """Get a single file asset by its storage path."""
        result = await db.execute(select(FileAsset).where(FileAsset.storage_path == storage_path))
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Session-linked queries (via SessionAsset join)
    # ------------------------------------------------------------------

    async def get_by_session_id(self, db: AsyncSession, session_id: uuid.UUID) -> list[FileAsset]:
        """Get all files linked to a session."""
        result = await db.execute(
            select(FileAsset)
            .join(SessionAsset, SessionAsset.asset_id == FileAsset.id)
            .where(SessionAsset.session_id == session_id)
            .order_by(FileAsset.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_session_and_id(
        self, db: AsyncSession, session_id: uuid.UUID, file_id: uuid.UUID
    ) -> Optional[FileAsset]:
        """Get a file by session ID and file ID."""
        result = await db.execute(
            select(FileAsset)
            .join(SessionAsset, SessionAsset.asset_id == FileAsset.id)
            .where(
                and_(
                    FileAsset.id == file_id,
                    SessionAsset.session_id == session_id,
                )
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Image queries (media library)
    # ------------------------------------------------------------------

    async def get_user_images(
        self, db: AsyncSession, user_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[FileAsset]:
        """Get image files for a user with pagination."""
        image_filter = or_(
            FileAsset.content_type.is_(None),
            FileAsset.content_type.ilike("image%"),
        )
        result = await db.execute(
            select(FileAsset)
            .where(
                and_(
                    FileAsset.user_id == user_id,
                    FileAsset.upload_status == UploadStatus.COMPLETE,
                    image_filter,
                )
            )
            .order_by(FileAsset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_user_images(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """Count image files for a user."""
        image_filter = or_(
            FileAsset.content_type.is_(None),
            FileAsset.content_type.ilike("image%"),
        )
        result = await db.execute(
            select(func.count())
            .select_from(FileAsset)
            .where(
                and_(
                    FileAsset.user_id == user_id,
                    FileAsset.upload_status == UploadStatus.COMPLETE,
                    image_filter,
                )
            )
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Upload status lifecycle
    # ------------------------------------------------------------------

    async def mark_complete(self, db: AsyncSession, file_id: uuid.UUID) -> Optional[FileAsset]:
        """Mark an upload as complete."""
        asset = await self.get_by_id(db, file_id)
        if not asset:
            return None
        asset.upload_status = UploadStatus.COMPLETE
        await db.flush()
        return asset

    async def mark_failed(self, db: AsyncSession, file_id: uuid.UUID) -> None:
        """Mark an upload as failed."""
        asset = await self.get_by_id(db, file_id)
        if not asset:
            return
        asset.upload_status = UploadStatus.FAILED
        await db.flush()

    # ------------------------------------------------------------------
    # SessionAsset link management
    # ------------------------------------------------------------------

    async def link_to_session(
        self, db: AsyncSession, file_id: uuid.UUID, session_id: uuid.UUID
    ) -> SessionAsset:
        """Link a file to a session. Returns existing link if already linked."""
        existing = await db.execute(
            select(SessionAsset).where(
                and_(
                    SessionAsset.asset_id == file_id,
                    SessionAsset.session_id == session_id,
                )
            )
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return row

        link = SessionAsset(asset_id=file_id, session_id=session_id)
        db.add(link)
        await db.flush()
        await db.refresh(link)
        return link

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_asset(self, db: AsyncSession, file_id: uuid.UUID) -> None:
        """Hard-delete a single asset (cascades to session links)."""
        await db.execute(delete(FileAsset).where(FileAsset.id == file_id))
        await db.flush()

    async def delete_user_assets(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """GDPR: delete all assets belonging to a user."""
        result = await db.execute(delete(FileAsset).where(FileAsset.user_id == user_id))
        await db.flush()
        return result.rowcount
