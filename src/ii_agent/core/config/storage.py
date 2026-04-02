"""Storage configuration settings."""

from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Type aliases
StorageProvider = Literal["gcs", "local", "s3"]


class StorageSettings(BaseSettings):
    """File storage configuration for various storage backends.

    Environment variables use STORAGE_ prefix:
        STORAGE_PROVIDER: Storage provider ("gcs", "local", "s3")
        STORAGE_FILE_UPLOAD_PROJECT_ID: GCS project ID for file uploads
        STORAGE_FILE_UPLOAD_BUCKET_NAME: GCS bucket name for file uploads
        STORAGE_FILE_UPLOAD_SIZE_LIMIT: Maximum file upload size in bytes
        STORAGE_CUSTOM_DOMAIN: Custom domain for file URLs

    Example .env:
        STORAGE_PROVIDER=gcs
        STORAGE_FILE_UPLOAD_PROJECT_ID=my-project
        STORAGE_FILE_UPLOAD_BUCKET_NAME=my-bucket
        STORAGE_FILE_UPLOAD_SIZE_LIMIT=104857600  # 100MB
        STORAGE_CUSTOM_DOMAIN=files.example.com
    """

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider settings
    provider: StorageProvider = Field(
        default="gcs",
        description="Storage provider (gcs, local, s3)",
    )

    # File upload storage (main storage)
    file_upload_project_id: Optional[str] = Field(
        default=None,
        description="GCS project ID for file uploads",
    )

    file_upload_bucket_name: Optional[str] = Field(
        default=None,
        description="GCS bucket name for file uploads",
    )

    file_upload_size_limit: int = Field(
        default=100 * 1024 * 1024,  # 100MB
        description="Maximum file upload size in bytes",
        gt=0,
    )

    # Avatar storage
    avatar_project_id: Optional[str] = Field(
        default=None,
        description="GCS project ID for user avatars",
    )

    avatar_bucket_name: Optional[str] = Field(
        default=None,
        description="GCS bucket name for user avatars",
    )

    # Slide assets storage (for presentations)
    slide_assets_project_id: Optional[str] = Field(
        default=None,
        description="GCS project ID for slide assets",
    )

    slide_assets_bucket_name: Optional[str] = Field(
        default=None,
        description="GCS bucket name for slide assets",
    )

    # Media storage (images, videos, audio)
    media_project_id: Optional[str] = Field(
        default=None,
        description="GCS project ID for media files",
    )

    media_bucket_name: Optional[str] = Field(
        default=None,
        description="GCS bucket name for media files",
    )

    # Custom domain for permanent URLs
    custom_domain: Optional[str] = Field(
        default=None,
        description="Custom domain for permanent file URLs (e.g., 'files.yourdomain.com')",
    )

    # Local file store settings (for development)
    file_store: str = Field(
        default="local",
        description="Local file store type",
    )

    file_store_path: str = Field(
        default="~/.ii_agent",
        description="Local file store path",
    )

    def validate_for_provider(self) -> None:
        """Validate configuration for the selected provider.

        Raises:
            ValueError: If required configuration is missing for the provider.
        """
        if self.provider == "gcs":
            if not self.file_upload_project_id:
                raise ValueError(
                    "GCS project ID is required when using GCS provider. "
                    "Set STORAGE_FILE_UPLOAD_PROJECT_ID environment variable."
                )
            if not self.file_upload_bucket_name:
                raise ValueError(
                    "GCS bucket name is required when using GCS provider. "
                    "Set STORAGE_FILE_UPLOAD_BUCKET_NAME environment variable."
                )
