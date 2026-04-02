"""Configuration for slide generation."""

import os
from pydantic import BaseModel


class SlideGenerationConfig(BaseModel):
    """Configuration for slide generation using Gemini or other providers."""

    # Gemini API key for image generation
    gemini_api_key: str | None = None

    # Model name for Gemini image generation
    gemini_model_name: str = "gemini-3-pro-image-preview"

    # GCP project ID for GCS storage
    gcp_project_id: str | None = None

    # GCP location
    gcp_location: str | None = None

    # GCS bucket for storing generated slides
    gcs_output_bucket: str | None = None

    # Custom domain for permanent URLs (e.g., sfile.ii.inc)
    custom_domain: str | None = None

    # Blob name prefix for storing generated slides
    blob_name_prefix: str = "tmp/slide_generation"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Fall back to common environment variables used in the project
        if not self.gemini_api_key:
            self.gemini_api_key = os.environ.get("GEMINI_API_KEY")

        if not self.gcs_output_bucket:
            self.gcs_output_bucket = os.environ.get("SLIDE_ASSETS_BUCKET_NAME")

        if not self.gcp_project_id:
            self.gcp_project_id = os.environ.get("SLIDE_ASSETS_PROJECT_ID")

        if not self.custom_domain:
            self.custom_domain = os.environ.get("CUSTOM_DOMAIN")
