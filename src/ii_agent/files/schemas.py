"""Pydantic schemas (DTOs) for files domain."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class FileDataResponse(BaseModel):
    """Serialized file data."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    size: int
    content_type: Optional[str] = None
    storage_path: Optional[str] = None
    url: Optional[str] = None


class GenerateUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int


class GenerateUploadUrlResponse(BaseModel):
    id: str
    upload_url: str


class UploadCompleteRequest(BaseModel):
    id: str
    file_name: str
    file_size: int
    content_type: str
    session_id: str | None = None


class UploadCompleteResponse(BaseModel):
    file_url: str


class GenerateDownloadUrlsRequest(BaseModel):
    storage_paths: List[str]


class GenerateDownloadUrlsResponse(BaseModel):
    signed_urls: List[str | None]
    missing_paths: List[str] = []
    file_ids: List[str | None] = []


class MediaLibraryItem(BaseModel):
    id: str
    name: str
    url: str
    source: Literal["upload", "generated"]
    created_at: datetime


class MediaLibraryResponse(BaseModel):
    items: List[MediaLibraryItem]
    total: int
    limit: int
    offset: int
    has_more: bool
