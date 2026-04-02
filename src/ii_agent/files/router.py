"""File storage API endpoints."""

from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import JSONResponse

from ii_agent.core.dependencies import SettingsDep
from ii_agent.files.dependencies import (
    FileServiceDep,
    FileUploadStorageDep,
    AvatarStorageDep,
)

from ii_agent.auth.dependencies import CurrentUser
from ii_agent.core.dependencies import DBSession
from ii_agent.sessions.dependencies import SessionRepositoryDep
from ii_agent.core.exceptions import ValidationError
from ii_agent.files.exceptions import FileAccessDeniedError, FileUploadNotFoundError
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.files.schemas import (
    GenerateUploadUrlRequest,
    GenerateUploadUrlResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    GenerateDownloadUrlsRequest,
    GenerateDownloadUrlsResponse,
    MediaLibraryResponse,
)

router = APIRouter(tags=["files"])

MAX_USER_MEDIA_PAGE_SIZE = 50
DEFAULT_USER_MEDIA_PAGE_SIZE = 12


@router.post("/chat/generate-upload-url", response_model=GenerateUploadUrlResponse)
async def generate_upload_url(
    upload_request: GenerateUploadUrlRequest,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    upload_storage: FileUploadStorageDep,
    db: DBSession,
    settings: SettingsDep,
):
    """Generate a signed URL for uploading a file to the object storage."""
    return await file_service.generate_upload_url(
        db,
        user_id=current_user.id,
        file_name=upload_request.file_name,
        content_type=upload_request.content_type,
        file_size=upload_request.file_size,
        upload_storage=upload_storage,
        max_file_size=settings.storage.file_upload_size_limit,
    )


@router.post("/chat/upload-complete", response_model=UploadCompleteResponse)
async def upload_complete(
    upload_complete_request: UploadCompleteRequest,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    upload_storage: FileUploadStorageDep,
    session_repo: SessionRepositoryDep,
    db: DBSession,
):
    """Complete a file upload and generate a signed download URL."""
    # Validate session ownership when provided
    if upload_complete_request.session_id:
        session = await session_repo.get_by_id(db, upload_complete_request.session_id)
        if not session or session.user_id != str(current_user.id):
            raise SessionNotFoundError("Session not found or access denied")

    return await file_service.complete_upload(
        db,
        user_id=current_user.id,
        file_id=upload_complete_request.id,
        file_name=upload_complete_request.file_name,
        file_size=upload_complete_request.file_size,
        content_type=upload_complete_request.content_type,
        session_id=upload_complete_request.session_id,
        upload_storage=upload_storage,
    )


@router.get("/chat/files/{file_id}")
async def download_file(
    file_id: str,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
):
    """Download a file by file_id with async streaming."""
    try:
        return await file_service.get_file_stream(
            db, file_id, user_id=str(current_user.id)
        )
    except FileAccessDeniedError:
        raise FileUploadNotFoundError("File not found or access denied")


@router.get("/public/chat/{session_id}/files/{file_id}")
async def download_user_public_file(
    session_id: str,
    file_id: str,
    file_service: FileServiceDep,
    session_repo: SessionRepositoryDep,
    db: DBSession,
):
    """Download a file from a public session with async streaming."""
    session = await session_repo.get_public_by_id(db, session_id)
    if not session:
        raise SessionNotFoundError("Session not found or not public")

    return await file_service.get_public_file_stream(db, session.id, file_id)


@router.post("/chat/files/download-urls", response_model=GenerateDownloadUrlsResponse)
async def generate_download_urls(
    request: GenerateDownloadUrlsRequest,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
    settings: SettingsDep,
):
    """Generate signed download URLs for a list of storage paths owned by the user."""
    if not request.storage_paths:
        raise ValidationError("No storage paths provided")

    return await file_service.generate_download_urls(
        db,
        user_id=str(current_user.id),
        storage_paths=request.storage_paths,
        config_media_bucket=settings.storage.media_bucket_name,
        config_upload_bucket=settings.storage.file_upload_bucket_name,
    )


@router.get("/chat/user-media-library", response_model=MediaLibraryResponse)
async def list_user_media_library(
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
    settings: SettingsDep,
    limit: int = Query(
        DEFAULT_USER_MEDIA_PAGE_SIZE,
        ge=1,
        le=MAX_USER_MEDIA_PAGE_SIZE,
        description="Number of items to return",
    ),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Return all image uploads for the current user across all sessions."""
    return await file_service.get_media_library(
        db,
        user_id=str(current_user.id),
        limit=limit,
        offset=offset,
        config_media_bucket=settings.storage.media_bucket_name,
        config_upload_bucket=settings.storage.file_upload_bucket_name,
    )


@router.post("/avatar")
async def upload_avatar(
    db: DBSession,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    avatar_storage: AvatarStorageDep,
    file: UploadFile = File(...),
):
    """Upload or update an avatar image for the user."""
    file_extension = file.filename.split(".")[-1]

    url = await file_service.upload_avatar(
        db,
        user_id=current_user.id,
        file_content=file.file,
        file_extension=file_extension,
        avatar_storage=avatar_storage,
    )

    current_user.avatar = f"users/{current_user.id}/profile/avatar.{file_extension}"
    await db.commit()
    await db.refresh(current_user)

    return JSONResponse(
        status_code=200,
        content={"message": "Avatar uploaded successfully", "url": url},
    )


@router.get("/avatar")
async def get_avatar(
    current_user: CurrentUser,
    file_service: FileServiceDep,
    avatar_storage: AvatarStorageDep,
):
    """Get the avatar image for the user."""
    avatar_blob_name = current_user.avatar
    if not avatar_blob_name:
        raise FileUploadNotFoundError("No avatar image found")

    url = file_service.get_avatar_url(avatar_blob_name, avatar_storage)
    return JSONResponse(status_code=200, content={"url": url})
