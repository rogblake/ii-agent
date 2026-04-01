"""StorageService — domain-facing API that combines provider + path resolver.

Created once in ``ApplicationContainer.init()`` and accessed via
``ContainerDep`` in FastAPI routes::

    from ii_agent.core.storage.dependencies import StorageServiceDep

    @router.post("/upload")
    async def upload(storage: StorageServiceDep): ...
"""

from __future__ import annotations

import io
from typing import BinaryIO

from ii_agent.core.storage.path_resolver import PathResolver
from ii_agent.core.storage.providers.base import StorageProvider


class StorageService:
    """High-level storage API for all domains.

    Wraps :class:`StorageProvider` (I/O) + :class:`PathResolver` (path building)
    so callers never construct paths manually.
    """

    def __init__(
        self,
        provider: StorageProvider,
        paths: PathResolver,
    ) -> None:
        self._provider = provider
        self._paths = paths

    # ------------------------------------------------------------------
    # Provider pass-through (raw path)
    # ------------------------------------------------------------------

    @property
    def provider(self) -> StorageProvider:
        """Direct access to the underlying provider for raw-path operations."""
        return self._provider

    @property
    def paths(self) -> PathResolver:
        """Direct access to the path resolver."""
        return self._paths

    async def read(self, path: str) -> BinaryIO:
        return await self._provider.read(path)

    async def write(
        self, path: str, content: BinaryIO, content_type: str | None = None
    ) -> str:
        return await self._provider.write(path, content, content_type)

    async def write_from_url(
        self, source_url: str, path: str, content_type: str | None = None
    ) -> str:
        return await self._provider.write_from_url(source_url, path, content_type)

    async def exists(self, path: str) -> bool:
        return await self._provider.exists(path)

    async def size(self, path: str) -> int:
        return await self._provider.size(path)

    async def delete(self, path: str) -> None:
        await self._provider.delete(path)

    async def copy(self, source_path: str, dest_path: str) -> str:
        return await self._provider.copy(source_path, dest_path)

    async def signed_url(self, path: str, expiry_seconds: int = 3600) -> str:
        return await self._provider.signed_download_url(path, expiry_seconds)

    async def signed_urls_batch(
        self, paths: list[str], expiry_seconds: int = 3600
    ) -> list[str | None]:
        return await self._provider.signed_download_urls_batch(paths, expiry_seconds)

    async def signed_upload_url(
        self, path: str, content_type: str, expiry_seconds: int = 3600
    ) -> str:
        return await self._provider.signed_upload_url(path, content_type, expiry_seconds)

    def public_url(self, path: str) -> str:
        return self._provider.public_url(path)

    # ------------------------------------------------------------------
    # User files
    # ------------------------------------------------------------------

    async def upload_user_file(
        self,
        user_id: str,
        file_id: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        """Upload a user file. Returns the storage path."""
        path = self._paths.user_upload(user_id, file_id, ext)
        return await self._provider.write(path, content, content_type)

    async def upload_user_file_from_url(
        self,
        user_id: str,
        file_id: str,
        ext: str,
        source_url: str,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.user_upload(user_id, file_id, ext)
        return await self._provider.write_from_url(source_url, path, content_type)

    async def upload_user_generated(
        self,
        user_id: str,
        file_id: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.user_generated(user_id, file_id, ext)
        return await self._provider.write(path, content, content_type)

    async def upload_user_generated_from_url(
        self,
        user_id: str,
        file_id: str,
        ext: str,
        source_url: str,
        content_type: str | None = None,
    ) -> str:
        """Download from URL and store as user generated content. Returns path."""
        path = self._paths.user_generated(user_id, file_id, ext)
        return await self._provider.write_from_url(source_url, path, content_type)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    async def upload_skill(
        self,
        user_id: str,
        skill_name: str,
        zip_content: bytes,
    ) -> str:
        """Upload a skill zip to GCS. Returns the storage path."""
        path = self._paths.user_skill(user_id, skill_name)
        buf = io.BytesIO(zip_content)
        return await self._provider.write(path, buf, "application/zip")

    async def download_skill(
        self,
        user_id: str,
        skill_name: str,
    ) -> bytes:
        """Download a skill zip from GCS. Returns bytes."""
        path = self._paths.user_skill(user_id, skill_name)
        data = await self._provider.read(path)
        return data.read()

    async def skill_exists(
        self,
        user_id: str,
        skill_name: str,
    ) -> bool:
        """Check if a skill zip exists in storage."""
        path = self._paths.user_skill(user_id, skill_name)
        return await self._provider.exists(path)

    async def delete_skill(
        self,
        user_id: str,
        skill_name: str,
    ) -> None:
        """Delete a skill zip from storage."""
        path = self._paths.user_skill(user_id, skill_name)
        await self._provider.delete(path)

    def skill_path(self, user_id: str, skill_name: str) -> str:
        """Return the storage path for a skill (no I/O)."""
        return self._paths.user_skill(user_id, skill_name)

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    async def upload_content_template(
        self,
        category: str,
        filename: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.content_template(category, filename, ext)
        return await self._provider.write(path, content, content_type)

    # ------------------------------------------------------------------
    # Slides
    # ------------------------------------------------------------------

    async def upload_slide_asset(
        self,
        content_hash: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.slide_asset(content_hash, ext)
        return await self._provider.write(path, content, content_type)

    async def upload_slide_design(
        self,
        design_id: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.slide_design(design_id, ext)
        return await self._provider.write(path, content, content_type)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def upload_avatar(
        self,
        user_id: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.public_avatar(user_id, ext)
        return await self._provider.write(path, content, content_type)

    def avatar_url(self, user_id: str, ext: str) -> str:
        path = self._paths.public_avatar(user_id, ext)
        return self._provider.public_url(path)

    async def publish(self, source_path: str, asset_id: str, ext: str) -> str:
        """Copy a private asset to public/shared/ and return the public URL."""
        dest = self._paths.public_shared(asset_id, ext)
        await self._provider.copy(source_path, dest)
        return self._provider.public_url(dest)

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    async def upload_system_asset(
        self,
        category: str,
        filename: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.system_asset(category, filename, ext)
        return await self._provider.write(path, content, content_type)

    # ------------------------------------------------------------------
    # Temp
    # ------------------------------------------------------------------

    async def upload_temp(
        self,
        token: str,
        filename: str,
        ext: str,
        content: BinaryIO,
        content_type: str | None = None,
    ) -> str:
        path = self._paths.temp_file(token, filename, ext)
        return await self._provider.write(path, content, content_type)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_public(self, path: str) -> bool:
        return self._paths.is_public(path)
