"""Pure-Python path builder for storage objects. No I/O.

All storage paths go through here — single source of truth for the
subfolder structure within the bucket.

DB (user_assets) tracks metadata: source, content_type, file_name.
Storage path encodes only: scope + content category + unique file ID.

    bucket/
    ├── users/{user_id}/
    │   ├── media/{file_id}.{ext}       ← images, videos, audio
    │   ├── docs/{file_id}.{ext}        ← documents, code, other
    │   ├── avatars/{file_id}.{ext}     ← user profile pictures
    │   └── skills/{skill_name}.zip     ← custom skill packages
    │
    ├── content/
    │   ├── templates/{category}/{filename}.{ext}
    │   └── slides/{content_hash}.{ext}
    │
    ├── system/{category}/{filename}.{ext}
    │
    └── tmp/{token}/{filename}.{ext}
"""

from __future__ import annotations

import uuid


# Mapping from AssetType string values to storage folder names.
# Accepts str values matching files.types.AssetType (StrEnum inherits
# from str), keeping core/storage free from files-domain imports.
_MEDIA_TYPES = frozenset({"image", "video", "audio"})

_TYPE_FOLDERS: dict[str, str] = {
    "image": "media",
    "video": "media",
    "audio": "media",
    "document": "docs",
    "code": "docs",
    "other": "docs",
}

_DEFAULT_FOLDER = "docs"


class PathResolver:
    """Pure-Python path builder for storage objects. No I/O."""

    # ── User content ──

    def user_file(
        self, user_id: uuid.UUID, asset_type: str, file_id: str, ext: str
    ) -> str:
        """Path for any user file, organized by content type.

        ``asset_type`` accepts :class:`~ii_agent.files.types.AssetType`
        values directly (StrEnum is str-compatible).
        """
        folder = _TYPE_FOLDERS.get(asset_type, _DEFAULT_FOLDER)
        return f"users/{user_id}/{folder}/{file_id}.{ext}"

    def user_avatar(
        self, user_id: uuid.UUID, file_id: str, ext: str
    ) -> str:
        return f"users/{user_id}/avatars/{file_id}.{ext}"

    def user_skill(self, user_id: uuid.UUID, skill_name: str) -> str:
        return f"users/{user_id}/skills/{skill_name}.zip"

    # ── Content ──

    def content_template(
        self, category: str, filename: str, ext: str
    ) -> str:
        return f"content/templates/{category}/{filename}.{ext}"

    def slide_asset(self, content_hash: str, ext: str) -> str:
        return f"content/slides/{content_hash}.{ext}"

    # ── System ──

    def system_asset(self, category: str, filename: str, ext: str) -> str:
        return f"system/{category}/{filename}.{ext}"

    # ── Temp ──

    def temp_file(self, token: str, filename: str, ext: str) -> str:
        return f"tmp/{token}/{filename}.{ext}"

    # ── Queries ──

    def is_user_content(self, path: str) -> bool:
        """True for any path under users/. Used to detect GCS-stored user data."""
        return path.startswith("users/")

    def user_prefix(self, user_id: uuid.UUID) -> str:
        return f"users/{user_id}/"

    def user_media_prefix(self, user_id: uuid.UUID) -> str:
        """Prefix for a user's media files (images, videos, audio)."""
        return f"users/{user_id}/media/"

    def user_type_prefix(
        self, user_id: uuid.UUID, asset_type: str
    ) -> str:
        """Prefix for a user's files of a given type."""
        folder = _TYPE_FOLDERS.get(asset_type, _DEFAULT_FOLDER)
        return f"users/{user_id}/{folder}/"


# Module-level singleton — stateless, safe to share
path_resolver = PathResolver()
