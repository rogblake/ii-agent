"""File asset API endpoints."""

import uuid

from fastapi import APIRouter, UploadFile, File, Query
from fastapi.responses import JSONResponse

from ii_agent.files.dependencies import FileServiceDep

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

router = APIRouter(prefix="/assets", tags=["assets"])

MAX_USER_MEDIA_PAGE_SIZE = 50
DEFAULT_USER_MEDIA_PAGE_SIZE = 12


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=GenerateUploadUrlResponse)
async def generate_upload_url(
    upload_request: GenerateUploadUrlRequest,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
):
    """Generate a signed URL for uploading a file to object storage."""
    return await file_service.generate_upload_url(
        db,
        user_id=current_user.id,
        file_name=upload_request.file_name,
        content_type=upload_request.content_type,
        file_size=upload_request.file_size,
    )


@router.post("/{asset_id}/complete", response_model=UploadCompleteResponse)
async def upload_complete(
    asset_id: uuid.UUID,
    upload_complete_request: UploadCompleteRequest,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    session_repo: SessionRepositoryDep,
    db: DBSession,
):
    """Complete a file upload and generate a signed download URL."""
    if upload_complete_request.session_id:
        session = await session_repo.get_by_id(db, upload_complete_request.session_id)
        if not session or session.user_id != current_user.id:
            raise SessionNotFoundError("Session not found or access denied")

    return await file_service.complete_upload(
        db,
        user_id=current_user.id,
        file_id=asset_id,
        file_name=upload_complete_request.file_name,
        file_size=upload_complete_request.file_size,
        content_type=upload_complete_request.content_type,
        session_id=upload_complete_request.session_id,
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


@router.get("/{asset_id}/download")
async def download_asset(
    asset_id: uuid.UUID,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
):
    """Download a file asset by ID with async streaming."""
    try:
        return await file_service.get_file_stream(
            db, asset_id, user_id=current_user.id
        )
    except FileAccessDeniedError:
        raise FileUploadNotFoundError("File not found or access denied")


@router.post("/download-urls", response_model=GenerateDownloadUrlsResponse)
async def generate_download_urls(
    request: GenerateDownloadUrlsRequest,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
):
    """Generate signed download URLs for a list of storage paths owned by the user."""
    if not request.storage_paths:
        raise ValidationError("No storage paths provided")

    return await file_service.generate_download_urls(
        db,
        user_id=current_user.id,
        storage_paths=request.storage_paths,
    )


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------


@router.get("/media-library", response_model=MediaLibraryResponse)
async def list_media_library(
    current_user: CurrentUser,
    file_service: FileServiceDep,
    db: DBSession,
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
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Avatar
# ---------------------------------------------------------------------------


@router.post("/avatar")
async def upload_avatar(
    db: DBSession,
    current_user: CurrentUser,
    file_service: FileServiceDep,
    file: UploadFile = File(...),
):
    """Upload or update an avatar image for the user."""
    file_extension = file.filename.split(".")[-1]

    url = await file_service.upload_avatar(
        db,
        user_id=current_user.id,
        file_content=file.file,
        file_extension=file_extension,
    )

    current_user.avatar = url
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
):
    """Get the avatar URL for the current user."""
    avatar_blob_name = current_user.avatar
    if not avatar_blob_name:
        raise FileUploadNotFoundError("No avatar image found")

    url = file_service.get_avatar_url(avatar_blob_name)
    return JSONResponse(status_code=200, content={"url": url})


# ---------------------------------------------------------------------------
# Public endpoints (served under /v1/public/sessions)
# ---------------------------------------------------------------------------

public_router = APIRouter(prefix="/sessions", tags=["Files Public"])


@public_router.get("/{session_id}/assets/{asset_id}")
async def download_public_asset(
    session_id: uuid.UUID,
    asset_id: uuid.UUID,
    file_service: FileServiceDep,
    session_repo: SessionRepositoryDep,
    db: DBSession,
):
    """Download a file from a public session with async streaming."""
    session = await session_repo.get_public_by_id(db, session_id)
    if not session:
        raise SessionNotFoundError("Session not found or not public")

    return await file_service.get_public_file_stream(db, session.id, asset_id)
