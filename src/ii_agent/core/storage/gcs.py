"""Google Cloud Storage provider implementation."""

import io
import requests
import datetime
from typing import BinaryIO
from google.cloud import storage
from google.auth import default
from google.auth import compute_engine
from google.auth.transport import requests as auth_requests
from .base import BaseStorage


class GCS(BaseStorage):
    """Google Cloud Storage provider for file storage."""

    def __init__(
        self, project_id: str, bucket_name: str, custom_domain: str | None = None
    ):
        # Get credentials with proper scopes for signing
        credentials, _ = default(
            scopes=["https://www.googleapis.com/auth/devstorage.full_control"]
        )

        self.client = storage.Client(project=project_id, credentials=credentials)
        self.bucket = self.client.bucket(bucket_name)
        self.custom_domain = custom_domain

        # Cache signer and service account email for efficient signed URL generation
        self._credentials = credentials
        self._signer = None
        self._service_account_email = None
        self._use_iam_signer = False
        self._initialize_signer()

    def _initialize_signer(self):
        """Initialize and cache the signer for efficient signed URL generation.

        Supports both SA key credentials (local signing) and WIF/compute engine
        credentials (IAM signBlob API).
        """
        try:
            # SA key credentials have a local signer
            if hasattr(self._credentials, "signer") and not isinstance(
                self._credentials, compute_engine.Credentials
            ):
                self._signer = self._credentials.signer
                if hasattr(self._credentials, "service_account_email"):
                    self._service_account_email = self._credentials.service_account_email
            # WIF / compute engine credentials: use IAM signBlob via access_token
            elif isinstance(self._credentials, compute_engine.Credentials):
                self._use_iam_signer = True
                # Refresh populates the real SA email (before refresh it's "default")
                auth_request = auth_requests.Request()
                self._credentials.refresh(auth_request)
                self._service_account_email = self._credentials.service_account_email
        except (AttributeError, ValueError):
            pass

    def write(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        # Get a reference to the blob (i.e., the file in GCS)
        blob = self.bucket.blob(path)

        # Reset file pointer to the beginning before uploading
        content.seek(0)

        blob.upload_from_file(content, content_type=content_type)

        return blob.public_url

    def write_from_url(
        self, url: str, path: str, content_type: str | None = None
    ) -> str:
        blob = self.bucket.blob(path)
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            blob.upload_from_file(response.raw, content_type=content_type)

        return blob.public_url

    def read(self, path: str) -> BinaryIO:
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )

        # Create an in-memory binary stream to hold the file data.
        file_obj = io.BytesIO()

        blob.download_to_file(file_obj)

        # Reset the stream's position to the beginning so it can be read from.
        file_obj.seek(0)

        return file_obj

    def _signed_url_kwargs(self, **extra) -> dict:
        """Build kwargs for generate_signed_url, handling both SA key and WIF."""
        kwargs = {"version": "v4", **extra}

        if self._signer and self._service_account_email:
            # SA key: pass credentials for local signing
            kwargs["credentials"] = self._credentials
        elif self._use_iam_signer and self._service_account_email:
            # WIF: use IAM signBlob API via access_token + service_account_email
            auth_request = auth_requests.Request()
            self._credentials.refresh(auth_request)
            kwargs["service_account_email"] = self._service_account_email
            kwargs["access_token"] = self._credentials.token

        return kwargs

    def get_download_signed_url(
        self, path: str, expiration_seconds: int = 3600
    ) -> str | None:
        blob = self.bucket.blob(path)

        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket_name}'."
            )

        kwargs = self._signed_url_kwargs(
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="GET",
        )

        url = blob.generate_signed_url(**kwargs)

        return url

    def get_upload_signed_url(
        self, path: str, content_type: str, expiration_seconds: int = 3600
    ) -> str | None:
        blob = self.bucket.blob(path)

        kwargs = self._signed_url_kwargs(
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="PUT",
            content_type=content_type,
        )

        url = blob.generate_signed_url(**kwargs)

        return url

    def get_download_signed_urls_batch(
        self, paths: list[str], expiration_seconds: int = 3600
    ) -> list[str | None]:
        """Generate signed URLs for multiple files efficiently.

        This method reuses the cached signer and credentials for all URLs,
        avoiding repeated credential discovery and signer initialization overhead.
        This is significantly more efficient than calling get_download_signed_url
        in a loop or using thread pools.

        Args:
            paths: List of file paths in the bucket
            expiration_seconds: Time in seconds until the URL expires

        Returns:
            List of signed URLs (or None for files that don't exist)

        Performance: This method generates URLs through pure cryptographic signing
        without making network requests per file, making it safe for generating
        hundreds or thousands of URLs without connection pool exhaustion.

        Note: Images with paths starting with "sessions/" are generated images.
        If this storage client points at the public media bucket, the method
        returns public URLs; otherwise it falls back to signed URLs.
        """
        if not paths:
            return []

        base_kwargs = self._signed_url_kwargs(
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="GET",
        )
        urls: list[str | None] = []

        public_sessions_bucket = self.bucket.name == "ii-agent-public"

        for path in paths:
            try:
                # Use public URLs for sessions/* only when the bucket is public.
                if path.startswith("sessions/") and public_sessions_bucket:
                    url = f"https://storage.googleapis.com/{self.bucket.name}/{path}"
                    urls.append(url)
                    continue

                blob = self.bucket.blob(path)

                # Skip existence check to avoid network calls
                # The signed URL will be valid regardless of file existence
                # Clients should handle 404s when accessing the URL
                url = blob.generate_signed_url(**base_kwargs)
                urls.append(url)
            except Exception:
                # If signing fails for any reason, append None
                urls.append(None)

        return urls

    def is_exists(self, path: str) -> bool:
        blob = self.bucket.blob(path)
        return blob.exists()

    def get_file_size(self, path: str) -> int:
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )
        blob.reload()
        return blob.size

    def get_public_url(self, path: str) -> str:
        # NOTE: assume that the blob is already public
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )

        return blob.public_url

    def get_permanent_url(self, path: str) -> str:
        """Get permanent URL using custom domain or standard public URL."""
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )

        # Make blob public if it isn't already
        try:
            blob.make_public()
        except Exception:
            # If already public or permission error, continue
            pass

        if self.custom_domain:
            return f"https://{self.custom_domain}/{path}"
        else:
            return blob.public_url

    def upload_and_get_permanent_url(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        """Upload file and return permanent URL."""
        # Upload the file
        blob = self.bucket.blob(path)
        content.seek(0)
        blob.upload_from_file(content, content_type=content_type)

        # Set cache control for better CDN performance
        blob.cache_control = "public, max-age=31536000"  # Cache for 1 year
        blob.patch()

        # Make the file publicly accessible
        try:
            blob.make_public()
        except Exception:
            # If already public or permission error, continue
            pass

        # Return permanent URL
        if self.custom_domain:
            return f"https://{self.custom_domain}/{path}"
        else:
            return blob.public_url