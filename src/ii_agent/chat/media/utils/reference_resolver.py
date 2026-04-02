"""Utility for resolving media references and session images."""

from __future__ import annotations

import logging
import uuid
from typing import Any, List, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.files.models import FileAsset, SessionAsset
from ii_agent.files.types import AssetSource, AssetType
from ii_agent.chat.types import MediaReference
from ii_agent.chat.api.schemas import AdvancedModeReference

if TYPE_CHECKING:
    from ii_agent.files.service import FileService

logger = logging.getLogger(__name__)


class ReferenceResolver:
    """Handles resolution of media references to signed URLs."""

    @staticmethod
    async def resolve_references(
        db_session: AsyncSession,
        references: list[MediaReference] | list[dict[str, Any]] | None,
        *,
        file_service: FileService | None = None,
    ) -> list[AdvancedModeReference]:
        """
        Attach signed URLs to stored references via FileService.

        Args:
            db_session: Database session
            references: List of MediaReference objects or dicts with file_id and type
            file_service: FileService instance for cached signed URL resolution.
                          If not provided, falls back to ``get_app_container().file_service``.

        Returns:
            List of AdvancedModeReference with signed URLs attached
        """
        if not references:
            return []

        file_ids: list[str] = []
        for ref in references:
            if isinstance(ref, MediaReference):
                file_ids.append(ref.file_id)
            elif isinstance(ref, dict):
                fid = ref.get("file_id")
                if isinstance(fid, str):
                    file_ids.append(fid)

        if not file_ids:
            return []

        # Resolve FileService if not provided
        if file_service is None:
            from ii_agent.core.container import get_app_container

            file_service = get_app_container().file_service

        # Batch-resolve signed URLs via FileService (cached + DB-persisted)
        file_urls: dict[str, str | None] = {}
        try:
            uuid_ids = [uuid.UUID(fid) for fid in file_ids]
            url_map = await file_service.resolve_signed_urls(db_session, uuid_ids)
            for fid_uuid, url in url_map.items():
                file_urls[str(fid_uuid)] = url
        except Exception as e:
            logger.error("Batch URL resolution failed: %s", e, exc_info=True)

        # Build final resolved references
        resolved: list[AdvancedModeReference] = []
        for ref in references:
            file_id = ref.file_id if isinstance(ref, MediaReference) else ref.get("file_id")
            ref_type = ref.type if isinstance(ref, MediaReference) else ref.get("type")
            file_url = file_urls.get(file_id) if file_id else None

            resolved.append(
                AdvancedModeReference(
                    file_id=file_id,
                    type=ref_type,
                    file_url=file_url,
                )
            )

        return resolved

    @staticmethod
    async def get_session_images(
        db_session: AsyncSession,
        session_id: uuid.UUID,
    ) -> List[str]:
        """
        Get all generated images from conversation history in this session.

        Returns list of file_ids for images that were generated (not uploaded by user).
        Generated images are identified by source=GENERATED and asset_type=IMAGE.

        Args:
            db_session: Database session
            session_id: Session ID

        Returns:
            List of file_ids for generated images
        """
        try:
            # Query FileAsset table for generated images in this session
            result = await db_session.execute(
                select(FileAsset)
                .join(SessionAsset, SessionAsset.asset_id == FileAsset.id)
                .where(
                    SessionAsset.session_id == session_id,
                    FileAsset.source == AssetSource.GENERATED,
                    FileAsset.asset_type == AssetType.IMAGE,
                )
                .order_by(FileAsset.created_at.asc())
            )
            generated_files = result.scalars().all()

            file_ids = [str(file.id) for file in generated_files]
            logger.info(f"Found {len(file_ids)} generated images in session {session_id}")
            return file_ids

        except Exception as e:
            logger.error(
                f"Error fetching generated images for session {session_id}: {e}", exc_info=True
            )
            return []
