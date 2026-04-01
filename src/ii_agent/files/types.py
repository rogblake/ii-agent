"""File domain enums."""

from enum import StrEnum


class AssetType(StrEnum):
    """Broad media classification for stored files."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    CODE = "code"
    OTHER = "other"


class AssetSource(StrEnum):
    """How the file was created."""

    USER_UPLOAD = "user_upload"
    GENERATED = "generated"
    SYSTEM = "system"


class UploadStatus(StrEnum):
    """Tracks the lifecycle of a file upload."""

    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
