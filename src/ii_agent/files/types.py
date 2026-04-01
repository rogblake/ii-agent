"""File domain enums."""

from __future__ import annotations

from enum import StrEnum


_IMAGE_EXTS = frozenset({
    "png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico",
    "tiff", "tif", "heic", "heif", "avif",
})
_VIDEO_EXTS = frozenset({
    "mp4", "mov", "avi", "mkv", "webm", "flv", "wmv", "m4v", "3gp",
})
_AUDIO_EXTS = frozenset({
    "mp3", "wav", "ogg", "flac", "aac", "m4a", "wma", "opus",
})
_DOCUMENT_EXTS = frozenset({
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "csv", "rtf", "odt", "ods", "odp",
})
_CODE_EXTS = frozenset({
    "py", "js", "ts", "jsx", "tsx", "html", "css", "json", "yaml",
    "yml", "xml", "sh", "bash", "sql", "go", "rs", "java", "kt",
    "swift", "c", "cpp", "h", "hpp", "rb", "php", "md", "tex",
})


class AssetType(StrEnum):
    """Broad media classification for stored files."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    CODE = "code"
    OTHER = "other"

    @classmethod
    def from_content_type(cls, content_type: str | None) -> AssetType:
        """Infer AssetType from a MIME content type string."""
        if not content_type:
            return cls.OTHER
        ct = content_type.split(";", 1)[0].strip().lower()
        if ct.startswith("image/"):
            return cls.IMAGE
        if ct.startswith("video/"):
            return cls.VIDEO
        if ct.startswith("audio/"):
            return cls.AUDIO
        if ct.startswith("text/"):
            return cls.DOCUMENT
        if ct in (
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ):
            return cls.DOCUMENT
        return cls.OTHER

    @classmethod
    def from_ext(cls, ext: str) -> AssetType:
        """Infer AssetType from a file extension (with or without leading dot)."""
        ext = ext.lower().lstrip(".")
        if ext in _IMAGE_EXTS:
            return cls.IMAGE
        if ext in _VIDEO_EXTS:
            return cls.VIDEO
        if ext in _AUDIO_EXTS:
            return cls.AUDIO
        if ext in _DOCUMENT_EXTS:
            return cls.DOCUMENT
        if ext in _CODE_EXTS:
            return cls.CODE
        return cls.OTHER

    @property
    def is_media(self) -> bool:
        """True for image, video, audio — maps to ``media/`` storage folder."""
        return self in (AssetType.IMAGE, AssetType.VIDEO, AssetType.AUDIO)

    @property
    def is_image(self) -> bool:
        return self == AssetType.IMAGE


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
