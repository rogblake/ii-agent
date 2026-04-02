"""Service layer for files domain - business logic only."""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator, List, Optional

import anyio
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.files.exceptions import (
    FileAccessDeniedError,
    FileUploadNotFoundError,
    FileSizeLimitExceededError,
)
from ii_agent.files.models import FileUpload
from ii_agent.files.repository import FileRepository
from ii_agent.files.schemas import (
    FileDataResponse,
    GenerateDownloadUrlsResponse,
    GenerateUploadUrlResponse,
    MediaLibraryItem,
    MediaLibraryResponse,
    UploadCompleteResponse,
)
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.repository import SessionRepository
from ii_agent.core.storage import BaseStorage
from ii_agent.core.storage.locations import get_session_file_path


# Constants for file processing
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
SEVEN_DAY_SECONDS = 7 * 24 * 3600

class FileService:
    """Service for managing file uploads - business logic layer."""

    def __init__(
        self,
        *,
        file_repo: FileRepository,
        session_repo: SessionRepository,
        file_store: BaseStorage,
        media_store: BaseStorage | None,
        config: Settings,
    ) -> None:
        self._config = config
        self._file_repo = file_repo
        self._session_repo = session_repo
        self._storage = file_store
        self._media_storage = media_store

    def _get_storage_for_path(self, storage_path: str) -> BaseStorage:
        """Get the appropriate storage client for a given path."""
        if self._media_storage and storage_path.startswith("sessions/"):
            return self._media_storage
        return self._storage

    def _get_file_url(self, storage_path: str | None) -> str | None:
        """Get file URL from storage_path."""
        if not storage_path:
            return None
        if storage_path.startswith("http://") or storage_path.startswith("https://"):
            return storage_path
        storage_client = self._get_storage_for_path(storage_path)
        return storage_client.get_download_signed_url(storage_path)

    def _to_file_data(self, file: FileUpload) -> FileDataResponse:
        """Convert a FileUpload model to FileDataResponse."""
        return FileDataResponse(
            id=file.id,
            name=file.file_name,
            size=file.file_size,
            content_type=file.content_type,
            storage_path=file.storage_path,
            url=self._get_file_url(file.storage_path),
        )

    # ==================== File CRUD ====================

    async def get_file_by_id(self, db: AsyncSession, file_id: str) -> FileDataResponse:
        """Get file by ID and return FileDataResponse."""
        file = await self._file_repo.get_by_id(db, file_id)
        if not file:
            raise FileUploadNotFoundError(file_id)
        return self._to_file_data(file)

    async def get_files_by_session_id(
        self, db: AsyncSession, session_id: str
    ) -> List[FileDataResponse]:
        """Get all files for a session and return FileDataResponse list."""
        files = await self._file_repo.get_by_session_id(db, session_id)
        return [self._to_file_data(file) for file in files]

    async def update_file_session_id(
        self, db: AsyncSession, file_id: str, session_id: str
    ) -> bool:
        """Update file session ID."""
        return await self._file_repo.update_session_id(db, file_id, session_id)

    async def create_file_record(
        self,
        db: AsyncSession,
        *,
        file_id: str,
        file_name: str,
        file_size: int,
        storage_path: str,
        content_type: str,
        session_id: str,
    ) -> FileUpload:
        """Create a file upload record, resolving user_id from session_id.

        Convenience method for callers that don't have user_id available.
        """
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")

        return await self._file_repo.create(
            db,
            file_id=file_id,
            user_id=session.user_id,
            file_name=file_name,
            file_size=file_size,
            storage_path=storage_path,
            content_type=content_type,
            session_id=session_id,
        )

    async def write_file_from_url(
        self,
        db: AsyncSession,
        *,
        url: str,
        file_name: str,
        file_size: int,
        content_type: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> FileDataResponse:
        """Write file from URL to storage and create database record.

        If user_id is not provided, it is resolved from session_id.
        """
        if not user_id:
            session = await self._session_repo.get_by_id(db, session_id)
            if not session:
                raise SessionNotFoundError(f"Session {session_id} not found")
            user_id = session.user_id

        file_id = str(uuid.uuid4())
        storage_path = get_session_file_path(session_id, file_id, file_name)

        file = await self._file_repo.create(
            db,
            file_id=file_id,
            user_id=user_id,
            file_name=file_name,
            file_size=file_size,
            storage_path=storage_path,
            content_type=content_type,
            session_id=session_id,
        )

        self._storage.write_from_url(url, storage_path, content_type)

        return self._to_file_data(file)

    # ==================== Agent File Helpers ====================

    async def get_files_by_ids_and_update_session(
        self,
        db: AsyncSession,
        *,
        file_ids: List[str],
        user_id: str,
        session_id: str,
        expiration_seconds: int = SEVEN_DAY_SECONDS,
    ) -> List[FileDataResponse]:
        """Fetch files by IDs, link them to the session, and return with signed URLs.

        For each file ID:
        1. Look up the file record.
        2. Update its ``session_id`` if not already set.
        3. Generate a signed download URL.

        Returns a list of :class:`FileDataResponse` objects.
        """
        results: List[FileDataResponse] = []
        for file_id in file_ids:
            file_record = await self._file_repo.get_by_id(db, file_id)
            if not file_record:
                continue
            # Link file to session if not already linked
            if not file_record.session_id or file_record.session_id != session_id:
                await self._file_repo.update_session_id(db, file_id, session_id)
            results.append(self._to_file_data(file_record))
        return results

    async def prepare_agent_files(
        self,
        db: AsyncSession,
        *,
        file_ids: List[str],
        user_id: str,
        session_id: str,
    ) -> tuple[list[dict], list[dict]]:
        """Fetch files by IDs and separate into images and generic files.

        Returns ``(image_dicts, file_dicts)`` where each dict contains keys
        that the handler can use to construct v1 ``Image`` / ``UrlFile`` objects
        without the file service depending on v1 types.

        Image dicts:  ``{"url": str, "mime_type": str}``
        File dicts:   ``{"id": str, "url": str, "filename": str}``
        """
        files_data = await self.get_files_by_ids_and_update_session(
            db,
            file_ids=file_ids,
            user_id=user_id,
            session_id=session_id,
        )

        images: list[dict] = []
        files: list[dict] = []

        for file_data in files_data:
            if not file_data.url:
                continue

            files.append({
                "id": file_data.id,
                "url": file_data.url,
                "filename": file_data.name,
            })

            if file_data.content_type in IMAGE_CONTENT_TYPES:
                images.append({
                    "url": file_data.url,
                    "mime_type": file_data.content_type,
                })

        return images, files

    # ==================== Upload/Download ====================

    async def generate_upload_url(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        file_name: str,
        content_type: str,
        file_size: int,
        upload_storage: BaseStorage,
        max_file_size: int,
    ) -> GenerateUploadUrlResponse:
        """Generate a signed URL for uploading a file."""
        if file_size > max_file_size:
            raise FileSizeLimitExceededError(file_size, max_file_size)

        file_id = str(uuid.uuid4())
        blob_name = f"users/{user_id}/uploads/{file_id}-{file_name}"
        signed_url = upload_storage.get_upload_signed_url(blob_name, content_type)

        return GenerateUploadUrlResponse(id=file_id, upload_url=signed_url)

    async def complete_upload(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        file_id: str,
        file_name: str,
        file_size: int,
        content_type: str,
        session_id: Optional[str],
        upload_storage: BaseStorage,
    ) -> UploadCompleteResponse:
        """Complete file upload: verify in storage, create DB record, return download URL."""
        blob_name = f"users/{user_id}/uploads/{file_id}-{file_name}"

        if not upload_storage.is_exists(blob_name):
            raise FileUploadNotFoundError(file_id)

        await self._file_repo.create(
            db,
            file_id=file_id,
            user_id=user_id,
            file_name=file_name,
            file_size=file_size,
            storage_path=blob_name,
            content_type=content_type,
            session_id=session_id,
        )

        signed_url = upload_storage.get_download_signed_url(blob_name)
        return UploadCompleteResponse(file_url=signed_url)

    async def get_file_stream(
        self, db: AsyncSession, file_id: str, *, user_id: str
    ) -> StreamingResponse:
        """Get a streaming response for file download, validating user ownership."""
        file_upload = await self._file_repo.get_by_id_and_user(db, file_id, user_id)
        if not file_upload:
            raise FileAccessDeniedError(file_id)
        return self._create_file_stream_response(file_upload)

    async def get_public_file_stream(
        self, db: AsyncSession, session_id: str, file_id: str
    ) -> StreamingResponse:
        """Get a streaming response for a public session file download."""
        file_upload = await self._file_repo.get_by_session_and_id(db, session_id, file_id)
        if not file_upload:
            raise FileUploadNotFoundError(file_id)
        return self._create_file_stream_response(file_upload)

    def _create_file_stream_response(self, file_upload: FileUpload) -> StreamingResponse:
        """Create a streaming response for file download."""
        storage_client = self._get_storage_for_path(file_upload.storage_path)

        async def file_stream() -> AsyncIterator[bytes]:
            file_obj = await anyio.to_thread.run_sync(
                storage_client.read, file_upload.storage_path
            )
            try:
                chunk_size = 64 * 1024
                while True:
                    chunk = await anyio.to_thread.run_sync(file_obj.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await anyio.to_thread.run_sync(file_obj.close)

        return StreamingResponse(
            file_stream(),
            media_type=file_upload.content_type or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{file_upload.file_name}"',
                "Content-Length": str(file_upload.file_size),
            },
        )

    # ==================== Download URLs (batch) ====================

    async def generate_download_urls(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        storage_paths: List[str],
        config_media_bucket: str | None = None,
        config_upload_bucket: str | None = None,
    ) -> GenerateDownloadUrlsResponse:
        """Generate signed download URLs for a list of storage paths owned by user."""
        normalized_paths = [path.lstrip("/") for path in storage_paths]

        file_uploads = await self._file_repo.get_by_user_and_paths(
            db, user_id, normalized_paths
        )
        file_map = {file.storage_path: file for file in file_uploads}

        files_to_sign: List[FileUpload] = []
        index_map: List[int] = []
        file_ids: List[str | None] = [None] * len(normalized_paths)
        missing_paths: List[str] = []

        for idx, path in enumerate(normalized_paths):
            file_upload = file_map.get(path)
            if file_upload:
                files_to_sign.append(file_upload)
                index_map.append(idx)
                file_ids[idx] = file_upload.id
            else:
                missing_paths.append(path)

        signed_subset = await self._get_download_signed_urls_batch(
            files_to_sign,
            force_signed=True,
            media_bucket_name=config_media_bucket,
            upload_bucket_name=config_upload_bucket,
        )
        signed_urls: List[str | None] = [None] * len(normalized_paths)

        for idx, url in zip(index_map, signed_subset):
            signed_urls[idx] = url

        return GenerateDownloadUrlsResponse(
            signed_urls=signed_urls,
            missing_paths=missing_paths,
            file_ids=file_ids,
        )

    # ==================== Media Library ====================

    async def get_media_library(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        limit: int,
        offset: int,
        config_media_bucket: str | None = None,
        config_upload_bucket: str | None = None,
    ) -> MediaLibraryResponse:
        """Return all image uploads for a user across all sessions."""
        total = await self._file_repo.count_user_images(db, user_id)
        file_uploads = await self._file_repo.get_user_images(
            db, user_id, limit=limit, offset=offset
        )

        signed_urls = await self._get_download_signed_urls_batch(
            file_uploads,
            media_bucket_name=config_media_bucket,
            upload_bucket_name=config_upload_bucket,
        )

        items: List[MediaLibraryItem] = []
        for file_upload, signed_url in zip(file_uploads, signed_urls):
            if not signed_url:
                continue
            items.append(
                MediaLibraryItem(
                    id=file_upload.id,
                    name=file_upload.file_name,
                    url=signed_url,
                    source="generated"
                    if file_upload.storage_path
                    and "generated" in file_upload.storage_path
                    else "upload",
                    created_at=file_upload.created_at,
                )
            )

        return MediaLibraryResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(file_uploads) < total,
        )

    # ==================== Avatar ====================

    async def upload_avatar(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        file_content,
        file_extension: str,
        avatar_storage: BaseStorage,
    ) -> str:
        """Upload or update an avatar image. Returns public URL."""
        destination_blob_name = f"users/{user_id}/profile/avatar.{file_extension}"
        avatar_storage.write(content=file_content, path=destination_blob_name)
        return avatar_storage.get_public_url(destination_blob_name)

    def get_avatar_url(
        self,
        avatar_blob_name: str,
        avatar_storage: BaseStorage,
    ) -> str:
        """Get the public URL for an avatar."""
        return avatar_storage.get_public_url(avatar_blob_name)

    # ==================== Internal Helpers ====================

    async def _get_download_signed_urls_batch(
        self,
        file_uploads: List[FileUpload],
        *,
        force_signed: bool = False,
        media_bucket_name: str | None = None,
        upload_bucket_name: str | None = None,
    ) -> List[str | None]:
        """Fetch usable URLs efficiently using batch operations."""
        if not file_uploads:
            return []

        results: List[str | None] = [None] * len(file_uploads)
        media_storage_indices: List[tuple[int, str]] = []
        file_storage_indices: List[tuple[int, str]] = []

        for idx, file_upload in enumerate(file_uploads):
            storage_path = file_upload.storage_path
            if not storage_path:
                results[idx] = None
            elif storage_path.startswith("http://") or storage_path.startswith(
                "https://"
            ):
                results[idx] = storage_path
            else:
                if storage_path.startswith("sessions/"):
                    media_storage_indices.append((idx, storage_path))
                else:
                    file_storage_indices.append((idx, storage_path))

        async def process_storage_batch(
            storage_client: BaseStorage,
            indices: List[tuple[int, str]],
            bucket_name: str | None,
        ) -> None:
            if not indices:
                return

            paths = [path for _, path in indices]

            try:
                loop = asyncio.get_event_loop()
                signed_urls = await loop.run_in_executor(
                    None, storage_client.get_download_signed_urls_batch, paths
                )

                for (idx, storage_path), signed_url in zip(indices, signed_urls):
                    if signed_url:
                        results[idx] = signed_url
                    elif not force_signed:
                        try:
                            results[idx] = storage_client.get_permanent_url(
                                storage_path
                            )
                        except Exception:
                            if bucket_name:
                                results[idx] = (
                                    f"https://storage.googleapis.com/{bucket_name}/{storage_path}"
                                )
                            else:
                                results[idx] = None

            except Exception:
                for idx, path in indices:
                    try:
                        results[idx] = storage_client.get_download_signed_url(path)
                    except Exception:
                        if not force_signed:
                            try:
                                results[idx] = storage_client.get_permanent_url(path)
                            except Exception:
                                if bucket_name:
                                    results[idx] = f"https://storage.googleapis.com/{bucket_name}/{path}"
                                else:
                                    results[idx] = None
                        else:
                            results[idx] = None

        media_client = self._media_storage or self._storage
        await asyncio.gather(
            process_storage_batch(
                media_client, media_storage_indices, media_bucket_name
            ),
            process_storage_batch(
                self._storage, file_storage_indices, upload_bucket_name
            ),
        )

        return results
