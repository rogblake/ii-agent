"""Pydantic schemas (DTOs) for files domain."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ii_agent.files.types import AssetSource, AssetType, UploadStatus


# ---------------------------------------------------------------------------
# Core file response
# ---------------------------------------------------------------------------


class FileDataResponse(BaseModel):
    """Serialized file data — used by most callers."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    size: Optional[int] = None
    content_type: Optional[str] = None
    storage_path: Optional[str] = None
    url: Optional[str] = None
    asset_type: AssetType = AssetType.OTHER
    source: AssetSource = AssetSource.USER_UPLOAD
    upload_status: UploadStatus = UploadStatus.COMPLETE
    is_public: bool = False
    sandbox_path: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Upload flow
# ---------------------------------------------------------------------------


class GenerateUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int


class GenerateUploadUrlResponse(BaseModel):
    id: UUID
    upload_url: str


class UploadCompleteRequest(BaseModel):
    id: UUID
    file_name: str
    file_size: int
    content_type: str
    session_id: UUID | None = None


class UploadCompleteResponse(BaseModel):
    file_url: str


# ---------------------------------------------------------------------------
# Download URLs
# ---------------------------------------------------------------------------


class GenerateDownloadUrlsRequest(BaseModel):
    storage_paths: list[str]


class GenerateDownloadUrlsResponse(BaseModel):
    signed_urls: list[str | None]
    missing_paths: list[str] = []
    file_ids: list[UUID | None] = []


# ---------------------------------------------------------------------------
# Media library
# ---------------------------------------------------------------------------


class MediaLibraryItem(BaseModel):
    id: UUID
    name: str
    url: str
    source: Literal["upload", "generated"]
    created_at: datetime


class MediaLibraryResponse(BaseModel):
    items: list[MediaLibraryItem]
    total: int
    limit: int
    offset: int
    has_more: bool


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


class PublishResponse(BaseModel):
    public_url: str
