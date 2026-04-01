"""Files domain — unified file/asset management."""

from ii_agent.files.exceptions import (
    FileAccessDeniedError,
    FileSizeLimitExceededError,
    FileStorageError,
    FileUploadNotFoundError,
)
from ii_agent.files.models import FileAsset, SessionAsset
from ii_agent.files.repository import FileRepository
from ii_agent.files.schemas import (
    FileDataResponse,
    GenerateDownloadUrlsRequest,
    GenerateDownloadUrlsResponse,
    GenerateUploadUrlRequest,
    GenerateUploadUrlResponse,
    MediaLibraryItem,
    MediaLibraryResponse,
    PublishResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
)
from ii_agent.files.media import Audio, File, Image, Video
from ii_agent.files.service import FileService
from ii_agent.files.types import AssetSource, AssetType, UploadStatus

__all__ = [
    # Exceptions
    "FileAccessDeniedError",
    "FileSizeLimitExceededError",
    "FileStorageError",
    "FileUploadNotFoundError",
    # Models
    "FileAsset",
    "SessionAsset",
    # Repository
    "FileRepository",
    # Schemas
    "FileDataResponse",
    "GenerateDownloadUrlsRequest",
    "GenerateDownloadUrlsResponse",
    "GenerateUploadUrlRequest",
    "GenerateUploadUrlResponse",
    "MediaLibraryItem",
    "MediaLibraryResponse",
    "PublishResponse",
    "UploadCompleteRequest",
    "UploadCompleteResponse",
    # Service
    "FileService",
    # Types (enums)
    "AssetSource",
    "AssetType",
    "UploadStatus",
    # Media types
    "Audio",
    "File",
    "Image",
    "Video",
]
