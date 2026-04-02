"""Utility for resolving media references and session images."""

import logging
from typing import Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.files.models import FileUpload
from ii_agent.chat.schemas import MediaReference, AdvancedModeReference
from ii_agent.core.storage.client import storage, media_storage

logger = logging.getLogger(__name__)


class ReferenceResolver:
    """Handles resolution of media references to signed URLs."""

    @staticmethod
    async def resolve_references(
        db_session: AsyncSession,
        references: list[MediaReference] | list[dict[str, Any]] | None,
    ) -> list[AdvancedModeReference]:
        """
        Attach signed URLs to stored references.

        Args:
            db_session: Database session
            references: List of MediaReference objects or dicts with file_id and type

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

        result = await db_session.execute(
            select(FileUpload).where(FileUpload.id.in_(file_ids))
        )
        uploads = {upload.id: upload for upload in result.scalars().all()}

        media_storage_paths = []
        private_storage_paths = []

        for ref in references:
            file_id = ref.file_id if isinstance(ref, MediaReference) else ref.get("file_id")
            if file_id and file_id in uploads:
                storage_path = uploads[file_id].storage_path

                # Group by storage type
                if storage_path and storage_path.startswith("sessions/"):
                    media_storage_paths.append((file_id, storage_path))
                else:
                    private_storage_paths.append((file_id, storage_path))

        # Batch generate signed URLs for better performance
        file_urls = {}

        if media_storage_paths:
            try:
                paths = [path for _, path in media_storage_paths]
                urls = media_storage.get_download_signed_urls_batch(paths)
                for (file_id, _), url in zip(media_storage_paths, urls):
                    file_urls[file_id] = url
            except Exception as e:
                logger.error("Batch URL generation failed for media storage: %s", e, exc_info=True)

        if private_storage_paths:
            try:
                paths = [path for _, path in private_storage_paths]
                urls = storage.get_download_signed_urls_batch(paths)
                for (file_id, _), url in zip(private_storage_paths, urls):
                    file_urls[file_id] = url
            except Exception as e:
                logger.error("Batch URL generation failed for private storage: %s", e, exc_info=True)

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
        session_id: str,
    ) -> List[str]:
        """
        Get all generated images from conversation history in this session.

        Returns list of file_ids for images that were generated (not uploaded by user).
        Generated images are identified by storage_path starting with 'sessions/{session_id}/generated/'

        Args:
            db_session: Database session
            session_id: Session ID

        Returns:
            List of file_ids for generated images
        """
        try:
            # Query FileUpload table for generated images in this session
            result = await db_session.execute(
                select(FileUpload)
                .where(
                    FileUpload.session_id == session_id,
                    FileUpload.storage_path.like(f"sessions/{session_id}/generated/%")
                )
                .order_by(FileUpload.created_at.asc())
            )
            generated_files = result.scalars().all()

            file_ids = [str(file.id) for file in generated_files]
            logger.info(
                f"Found {len(file_ids)} generated images in session {session_id}"
            )
            return file_ids

        except Exception as e:
            logger.error(
                f"Error fetching generated images for session {session_id}: {e}",
                exc_info=True
            )
            return []
