from __future__ import annotations

import abc
from typing import BinaryIO


class StorageProvider(abc.ABC):
    """Abstract storage provider. All methods async except public_url."""

    @abc.abstractmethod
    async def write(self, path: str, content: BinaryIO, content_type: str | None = None) -> str:
        """Upload content. Returns the storage path."""

    @abc.abstractmethod
    async def write_from_url(
        self, source_url: str, path: str, content_type: str | None = None
    ) -> str:
        """Download from URL and upload to storage. Returns path."""

    @abc.abstractmethod
    async def read(self, path: str) -> BinaryIO:
        """Download object. Returns BytesIO."""

    @abc.abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if object exists."""

    @abc.abstractmethod
    async def size(self, path: str) -> int:
        """Get object size in bytes."""

    @abc.abstractmethod
    async def delete(self, path: str) -> None:
        """Delete object."""

    @abc.abstractmethod
    async def copy(self, source_path: str, dest_path: str) -> str:
        """Server-side copy. Returns dest path."""

    @abc.abstractmethod
    async def signed_download_url(self, path: str, expiry_seconds: int = 3600) -> str:
        """Generate signed download URL."""

    @abc.abstractmethod
    async def signed_download_urls_batch(
        self, paths: list[str], expiry_seconds: int = 3600
    ) -> list[str | None]:
        """Generate signed download URLs for multiple paths."""

    @abc.abstractmethod
    async def signed_upload_url(
        self, path: str, content_type: str, expiry_seconds: int = 3600
    ) -> str:
        """Generate signed upload URL."""

    @abc.abstractmethod
    def public_url(self, path: str) -> str:
        """Sync. Returns public URL for object."""
