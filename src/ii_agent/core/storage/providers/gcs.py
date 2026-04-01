"""Google Cloud Storage provider — async wrapper around sync google-cloud-storage."""

from __future__ import annotations

import datetime
import io
from typing import BinaryIO

import httpx
from fastapi.concurrency import run_in_threadpool
from google.api_core.exceptions import Forbidden, NotFound
from google.auth import compute_engine, default
from google.auth.transport import requests as auth_requests
from google.cloud import storage

from ii_agent.core.storage.exceptions import (
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from ii_agent.core.storage.providers.base import StorageProvider


class GCSProvider(StorageProvider):
    """Async GCS provider using sync google-cloud-storage in a thread pool."""

    def __init__(
        self,
        project_id: str,
        bucket_name: str,
        custom_domain: str | None = None,
    ) -> None:
        credentials, _ = default(
            scopes=["https://www.googleapis.com/auth/devstorage.full_control"]
        )
        self._client = storage.Client(project=project_id, credentials=credentials)
        self._bucket = self._client.bucket(bucket_name)
        self._custom_domain = custom_domain

        # Signer / credential caching for signed-URL generation.
        self._credentials = credentials
        self._signer = None
        self._service_account_email: str | None = None
        self._use_iam_signer = False
        self._initialize_signer()

    # ------------------------------------------------------------------
    # Signer initialisation (ported from legacy GCS class)
    # ------------------------------------------------------------------

    def _initialize_signer(self) -> None:
        """Cache the signer for efficient signed-URL generation.

        Supports SA-key credentials (local signing) and WIF / compute-engine
        credentials (IAM signBlob API).
        """
        try:
            if hasattr(self._credentials, "signer") and not isinstance(
                self._credentials, compute_engine.Credentials
            ):
                self._signer = self._credentials.signer
                if hasattr(self._credentials, "service_account_email"):
                    self._service_account_email = (
                        self._credentials.service_account_email
                    )
            elif isinstance(self._credentials, compute_engine.Credentials):
                self._use_iam_signer = True
                auth_request = auth_requests.Request()
                self._credentials.refresh(auth_request)
                self._service_account_email = self._credentials.service_account_email
        except (AttributeError, ValueError):
            pass

    def _signed_url_kwargs(self, **extra: object) -> dict:
        """Build kwargs for ``generate_signed_url``, handling SA-key and WIF."""
        kwargs: dict = {"version": "v4", **extra}

        if self._signer and self._service_account_email:
            kwargs["credentials"] = self._credentials
        elif self._use_iam_signer and self._service_account_email:
            auth_request = auth_requests.Request()
            self._credentials.refresh(auth_request)
            kwargs["service_account_email"] = self._service_account_email
            kwargs["access_token"] = self._credentials.token

        return kwargs

    # ------------------------------------------------------------------
    # Helper: run sync in thread
    # ------------------------------------------------------------------

    @staticmethod
    async def _run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN003
        return await run_in_threadpool(fn, *args, **kwargs)

    # ------------------------------------------------------------------
    # StorageProvider interface
    # ------------------------------------------------------------------

    async def write(
        self, path: str, content: BinaryIO, content_type: str | None = None
    ) -> str:
        def _upload() -> str:
            blob = self._bucket.blob(path)
            content.seek(0)
            blob.upload_from_file(content, content_type=content_type)
            return path

        try:
            return await self._run_sync(_upload)
        except Forbidden as exc:
            raise StoragePermissionError(str(exc)) from exc

    async def write_from_url(
        self, source_url: str, path: str, content_type: str | None = None
    ) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(source_url)
            response.raise_for_status()
            data = io.BytesIO(response.content)

        def _upload() -> str:
            blob = self._bucket.blob(path)
            data.seek(0)
            blob.upload_from_file(data, content_type=content_type)
            return path

        try:
            return await self._run_sync(_upload)
        except Forbidden as exc:
            raise StoragePermissionError(str(exc)) from exc

    async def read(self, path: str) -> BinaryIO:
        def _download() -> BinaryIO:
            blob = self._bucket.blob(path)
            buf = io.BytesIO()
            try:
                blob.download_to_file(buf)
            except NotFound as exc:
                raise StorageObjectNotFoundError(
                    f"Object '{path}' not found in bucket '{self._bucket.name}'."
                ) from exc
            buf.seek(0)
            return buf

        return await self._run_sync(_download)

    async def exists(self, path: str) -> bool:
        def _exists() -> bool:
            blob = self._bucket.blob(path)
            return blob.exists()

        return await self._run_sync(_exists)

    async def size(self, path: str) -> int:
        def _size() -> int:
            blob = self._bucket.blob(path)
            if not blob.exists():
                raise StorageObjectNotFoundError(
                    f"Object '{path}' not found in bucket '{self._bucket.name}'."
                )
            blob.reload()
            return blob.size

        return await self._run_sync(_size)

    async def delete(self, path: str) -> None:
        def _delete() -> None:
            blob = self._bucket.blob(path)
            try:
                blob.delete()
            except NotFound as exc:
                raise StorageObjectNotFoundError(
                    f"Object '{path}' not found in bucket '{self._bucket.name}'."
                ) from exc

        await self._run_sync(_delete)

    async def copy(self, source_path: str, dest_path: str) -> str:
        def _copy() -> str:
            src_blob = self._bucket.blob(source_path)
            if not src_blob.exists():
                raise StorageObjectNotFoundError(
                    f"Source object '{source_path}' not found."
                )
            self._bucket.copy_blob(src_blob, self._bucket, dest_path)
            return dest_path

        return await self._run_sync(_copy)

    async def signed_download_url(
        self, path: str, expiry_seconds: int = 3600
    ) -> str:
        def _sign() -> str:
            blob = self._bucket.blob(path)
            kwargs = self._signed_url_kwargs(
                expiration=datetime.timedelta(seconds=expiry_seconds),
                method="GET",
            )
            return blob.generate_signed_url(**kwargs)

        return await self._run_sync(_sign)

    async def signed_download_urls_batch(
        self, paths: list[str], expiry_seconds: int = 3600
    ) -> list[str | None]:
        if not paths:
            return []

        def _sign_batch() -> list[str | None]:
            base_kwargs = self._signed_url_kwargs(
                expiration=datetime.timedelta(seconds=expiry_seconds),
                method="GET",
            )
            urls: list[str | None] = []
            for p in paths:
                try:
                    blob = self._bucket.blob(p)
                    url = blob.generate_signed_url(**base_kwargs)
                    urls.append(url)
                except Exception:
                    urls.append(None)
            return urls

        return await self._run_sync(_sign_batch)

    async def signed_upload_url(
        self, path: str, content_type: str, expiry_seconds: int = 3600
    ) -> str:
        def _sign() -> str:
            blob = self._bucket.blob(path)
            kwargs = self._signed_url_kwargs(
                expiration=datetime.timedelta(seconds=expiry_seconds),
                method="PUT",
                content_type=content_type,
            )
            return blob.generate_signed_url(**kwargs)

        return await self._run_sync(_sign)

    def public_url(self, path: str) -> str:
        return f"https://storage.googleapis.com/{self._bucket.name}/{path}"
