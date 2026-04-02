"""FastAPI dependencies for files domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.core.exceptions import InternalError
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.files.repository import FileRepository
from ii_agent.files.service import FileService
from ii_agent.core.storage import GCS, BaseStorage
from ii_agent.core.storage.client import storage, media_storage


# ==================== Repository Dependencies ====================


def get_file_repository() -> FileRepository:
    """Provide FileRepository instance."""
    return FileRepository()


FileRepositoryDep = Annotated[FileRepository, Depends(get_file_repository)]


# ==================== Service Dependencies ====================


def get_file_service(
    file_repo: FileRepositoryDep,
    session_repo: SessionRepositoryDep,
) -> FileService:
    """Provide FileService instance with explicit repo injection."""
    return FileService(
        file_repo=file_repo,
        session_repo=session_repo,
        file_store=storage,
        media_store=media_storage,
        config=get_settings(),
    )


FileServiceDep = Annotated[FileService, Depends(get_file_service)]


# ==================== Storage Dependencies ====================


async def get_file_upload_storage() -> BaseStorage:
    """Provide storage for file uploads (private bucket)."""
    settings = get_settings()
    if settings.storage.provider == "gcs":
        return GCS(
            settings.storage.file_upload_project_id,
            settings.storage.file_upload_bucket_name,
            settings.storage.custom_domain,
        )
    raise InternalError("Storage provider not supported")


FileUploadStorageDep = Annotated[BaseStorage, Depends(get_file_upload_storage)]


async def get_avatar_storage() -> BaseStorage:
    """Provide storage for avatar images."""
    settings = get_settings()
    if settings.storage.provider == "gcs":
        return GCS(
            settings.storage.avatar_project_id,
            settings.storage.avatar_bucket_name,
            settings.storage.custom_domain,
        )
    raise InternalError("Storage provider not supported")


AvatarStorageDep = Annotated[BaseStorage, Depends(get_avatar_storage)]


__all__ = [
    "get_file_repository",
    "get_file_service",
    "get_file_upload_storage",
    "get_avatar_storage",
    "FileRepositoryDep",
    "FileServiceDep",
    "FileUploadStorageDep",
    "AvatarStorageDep",
]
