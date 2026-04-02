"""Storage client initialization.

This module initializes storage clients lazily on first access so that
GCP secrets applied during FastAPI lifespan are visible.

Available clients:
- storage: Main file upload storage (no custom domain)
- media_storage: Media files storage (with custom domain)
- slide_storage: Slide/presentation assets storage (with custom domain)
"""

from ii_agent.core.config.settings import get_settings
from ii_agent.core.storage.factory import create_storage_client

_storage = None
_media_storage = None
_slide_storage = None


def _init_storage():
    global _storage, _media_storage, _slide_storage
    s = get_settings()

    _storage = create_storage_client(
        s.storage.provider,
        s.storage.file_upload_project_id,
        s.storage.file_upload_bucket_name,
    )

    _media_storage = create_storage_client(
        s.storage.provider,
        s.storage.media_project_id,
        s.storage.media_bucket_name,
        s.storage.custom_domain,
    )

    # Slide storage uses slide_assets bucket if configured, otherwise falls back to file_upload
    # Always includes custom_domain for permanent URLs
    _slide_storage = create_storage_client(
        s.storage.provider,
        s.storage.slide_assets_project_id or s.storage.file_upload_project_id,
        s.storage.slide_assets_bucket_name or s.storage.file_upload_bucket_name,
        s.storage.custom_domain,
    )


def __getattr__(name):
    if name in ("storage", "media_storage", "slide_storage"):
        if _storage is None:
            _init_storage()
        return {"storage": _storage, "media_storage": _media_storage, "slide_storage": _slide_storage}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def close_all_storage_clients() -> None:
    """Close all storage clients and release resources.

    Call this during application shutdown (e.g., in FastAPI lifespan).
    """
    if _storage is not None:
        _storage.close()
    if _media_storage is not None:
        _media_storage.close()
    if _slide_storage is not None:
        _slide_storage.close()


__all__ = ["storage", "media_storage", "slide_storage", "close_all_storage_clients"]
