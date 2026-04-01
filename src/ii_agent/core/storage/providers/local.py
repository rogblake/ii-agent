"""Local filesystem storage provider for development and testing."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import BinaryIO

import httpx

from ii_agent.core.storage.exceptions import StorageObjectNotFoundError
from ii_agent.core.storage.providers.base import StorageProvider


class LocalProvider(StorageProvider):
    """Filesystem-backed storage provider. Uses async file I/O via asyncio."""

    def __init__(self, base_dir: str, serve_url: str) -> None:
        self._base_dir = Path(base_dir)
        self._serve_url = serve_url.rstrip("/")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _full_path(self, path: str) -> Path:
        return self._base_dir / path

    # ------------------------------------------------------------------
    # StorageProvider interface
    # ------------------------------------------------------------------

    async def write(
        self, path: str, content: BinaryIO, content_type: str | None = None
    ) -> str:
        dest = self._full_path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        content.seek(0)
        dest.write_bytes(content.read())
        return path

    async def write_from_url(
        self, source_url: str, path: str, content_type: str | None = None
    ) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(source_url)
            response.raise_for_status()
            data = response.content

        dest = self._full_path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return path

    async def read(self, path: str) -> BinaryIO:
        fp = self._full_path(path)
        if not fp.exists():
            raise StorageObjectNotFoundError(
                f"Object '{path}' not found in local storage."
            )
        return io.BytesIO(fp.read_bytes())

    async def exists(self, path: str) -> bool:
        return self._full_path(path).exists()

    async def size(self, path: str) -> int:
        fp = self._full_path(path)
        if not fp.exists():
            raise StorageObjectNotFoundError(
                f"Object '{path}' not found in local storage."
            )
        return fp.stat().st_size

    async def delete(self, path: str) -> None:
        fp = self._full_path(path)
        if not fp.exists():
            raise StorageObjectNotFoundError(
                f"Object '{path}' not found in local storage."
            )
        fp.unlink()

    async def copy(self, source_path: str, dest_path: str) -> str:
        src = self._full_path(source_path)
        if not src.exists():
            raise StorageObjectNotFoundError(
                f"Source object '{source_path}' not found in local storage."
            )
        dest = self._full_path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return dest_path

    async def signed_download_url(
        self, path: str, expiry_seconds: int = 3600
    ) -> str:
        expires = int(time.time()) + expiry_seconds
        return f"{self._serve_url}/{path}?token=dev&expires={expires}"

    async def signed_download_urls_batch(
        self, paths: list[str], expiry_seconds: int = 3600
    ) -> list[str | None]:
        expires = int(time.time()) + expiry_seconds
        return [
            f"{self._serve_url}/{p}?token=dev&expires={expires}" for p in paths
        ]

    async def signed_upload_url(
        self, path: str, content_type: str, expiry_seconds: int = 3600
    ) -> str:
        expires = int(time.time()) + expiry_seconds
        return f"{self._serve_url}/{path}?token=dev&expires={expires}&content_type={content_type}"

    def public_url(self, path: str) -> str:
        return f"{self._serve_url}/{path}"
