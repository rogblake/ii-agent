"""
Google AI Studio (Gemini API) implementation of video generation client.

Uses the google-genai SDK with API key authentication for Veo models.
This is an alternative to VertexVideoGenerationClient which uses GCP service account auth.
"""

import asyncio
import os
import uuid
from io import BytesIO
from typing import Literal

import anyio
import httpx
from google import genai
from google.cloud import storage
from google.genai import types

from ii_agent.core.storage.path_resolver import path_resolver
from .base import (
    BaseVideoGenerationClient,
    VideoGenerationResult,
    VideoReferenceImage,
)


# Model name mapping from frontend model IDs to Veo API model names
VEO_MODELS = {
    "veo-3.1-premium": "veo-3.1-generate-preview",
    "veo-3.1": "veo-3.1-generate-preview",
    "veo-3.1-fast": "veo-3.1-fast-generate-preview",
    "veo-3.0": "veo-3.0-generate-001",
    "veo-3.0-fast": "veo-3.0-fast-generate-001",
    "veo-2.0": "veo-2.0-generate-001",
}

DEFAULT_MODEL = "veo-2.0-generate-001"

# Resolution-based pricing per second
# Docs: https://cloud.google.com/vertex-ai/generative-ai/pricing
VEO_PRICING = {
    # Veo 3.1 Standard
    "veo-3.1-generate-001": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
    "veo-3.1-generate-preview": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
    # Veo 3.1 Fast
    "veo-3.1-fast-generate-001": {"720p": 0.15, "1080p": 0.15, "4k": 0.35},
    "veo-3.1-fast-generate-preview": {"720p": 0.15, "1080p": 0.15, "4k": 0.35},
    # Veo 3.0 (flat pricing)
    "veo-3.0-generate-001": {"720p": 0.40, "1080p": 0.40, "4k": 0.40},
    "veo-3.0-fast-generate-001": {"720p": 0.25, "1080p": 0.25, "4k": 0.25},
    # Veo 2.0 (flat pricing)
    "veo-2.0-generate-001": {"720p": 0.35, "1080p": 0.35, "4k": 0.35},
}

DEFAULT_PRICE_PER_SECOND = 0.40


def get_price_per_second(model_name: str, resolution: str) -> float:
    """Get price per second based on model and resolution."""
    model_pricing = VEO_PRICING.get(model_name)
    if not model_pricing:
        return DEFAULT_PRICE_PER_SECOND

    # Normalize resolution
    if resolution in ("4k", "2160p"):
        res_key = "4k"
    elif resolution == "1080p":
        res_key = "1080p"
    else:
        res_key = "720p"

    return model_pricing.get(res_key, DEFAULT_PRICE_PER_SECOND)


class GeminiVideoGenerationClient(BaseVideoGenerationClient):
    """Google AI Studio implementation of video generation client using Veo models."""

    supports_long_generation: bool = True
    supports_extension_api: bool = True
    supports_audio: bool = True
    supports_end_frame: bool = True

    def __init__(
        self,
        api_key: str,
        output_bucket: str | None = None,
        custom_domain: str | None = None,
    ):
        """
        Initialize Google AI Studio client for video generation.

        Args:
            api_key: Google AI Studio API key
            model_name: Name of the model (veo-3.1, veo-3.0, veo-2.0, etc.)
            output_bucket: GCS bucket for storing videos (optional)
            custom_domain: Custom domain for public URLs (optional)
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.output_bucket = output_bucket or os.getenv("VIDEO_GENERATE_GCS_OUTPUT_BUCKET")
        self.custom_domain = custom_domain or os.getenv("CUSTOM_DOMAIN")
        # Initialize GCS bucket if configured
        self.bucket = None
        if self.output_bucket:
            try:
                gcs_client = storage.Client()
                self.bucket = gcs_client.bucket(self.output_bucket)
            except Exception:
                pass  # GCS not available, will use URI directly

    def _resolve_model_name(self, model_name: str | None) -> str:
        """Resolve frontend model ID to Veo API model name."""
        if not model_name:
            return DEFAULT_MODEL
        # Check if it's already an API model name
        if model_name in VEO_PRICING:
            return model_name
        # Map from frontend ID
        return VEO_MODELS.get(model_name, DEFAULT_MODEL)

    async def generate_video(
        self,
        prompt: str,
        model_name: str,
        aspect_ratio: Literal["16:9", "9:16"] = "16:9",
        duration_seconds: int = 5,
        resolution: str = "720p",
        audio_included: bool = False,
        # Frame URLs (passed directly to Veo API)
        start_frame: str | None = None,
        end_frame: str | None = None,
        session_id: str | None = None,
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list[VideoReferenceImage] | None = None,
        user_id: uuid.UUID | None = None,
        **kwargs,
    ) -> VideoGenerationResult:
        """
        Generate video from text prompt and/or reference frames.

        Supports Veo 3.x features:
        - Native audio generation (Veo 3.x)
        - Start frame (image-to-video)
        - End frame (frame interpolation) - Veo 3.1 only
        - Reference images (Veo 3.1 only)

        Args:
            prompt: Text description of the video to generate
            aspect_ratio: Video aspect ratio ("16:9" or "9:16")
            duration_seconds: Duration in seconds (max 8 per generation)
            resolution: Video resolution ("480p", "720p", "1080p")
            audio_included: Whether to include audio (Veo 3.x only)
            start_frame: URL of start frame image (https:// or gs://)
            end_frame: URL of end frame image (https:// or gs://)
            session_id: Session ID for storage path organization

        Returns:
            VideoGenerationResult with video URL and metadata
        """
        model_name = self._resolve_model_name(model_name)

        # Prepare start frame (image) if provided
        start_image = None
        if start_frame:
            start_image = await self._url_to_image(start_frame)

        # Prepare end frame if provided (Veo 3.1 feature)
        end_image = None
        if end_frame:
            end_image = await self._url_to_image(end_frame)

        # Build generation config using camelCase parameter names
        effective_duration = min(duration_seconds, 8)  # Max 8 seconds per generation

        config_kwargs = {
            "aspectRatio": aspect_ratio,
            "numberOfVideos": 1,
            "durationSeconds": effective_duration,
        }

        # Add audio generation for Veo 3.x models
        if audio_included and "veo-3" in model_name:
            config_kwargs["generateAudio"] = True

        # Add end frame (last frame) if provided - Veo 3.1 feature
        if end_image and "veo-3.1" in model_name:
            config_kwargs["lastFrame"] = end_image

        # Add negative prompt if provided
        if negative_prompt:
            config_kwargs["negativePrompt"] = negative_prompt

        # Add seed for reproducibility (Veo 3.x only)
        if seed is not None and "veo-3" in model_name:
            config_kwargs["seed"] = seed

        # Add reference images for style/content guidance (Veo 3.1 only)
        if reference_images and "veo-3.1" in model_name:
            ref_images_list = []
            for ref_img in reference_images:
                if not ref_img.url:
                    continue
                image = await self._url_to_image(ref_img.url)
                ref_images_list.append(
                    types.VideoGenerationReferenceImage(
                        image=image,
                        referenceType=ref_img.reference_type,
                    )
                )
            if ref_images_list:
                config_kwargs["referenceImages"] = ref_images_list

        config = types.GenerateVideosConfig(**config_kwargs)

        # Build source for video generation (newer API pattern)
        source_kwargs = {"prompt": prompt}
        if start_image:
            source_kwargs["image"] = start_image
        source = types.GenerateVideosSource(**source_kwargs)

        # Submit the operation using the source parameter
        operation = await self.client.aio.models.generate_videos(
            model=model_name,
            source=source,
            config=config,
        )

        # Poll for completion
        polling_interval_seconds = 5
        max_wait_time_seconds = 360  # 6 minutes for video generation
        elapsed_time = 0

        while not operation.done:
            if elapsed_time >= max_wait_time_seconds:
                raise TimeoutError(
                    f"Video generation timed out after {max_wait_time_seconds} seconds."
                )
            await asyncio.sleep(polling_interval_seconds)
            elapsed_time += polling_interval_seconds
            operation = self.client.operations.get(operation)

        # Process result
        if (
            operation.result
            and operation.result.generated_videos
            and operation.result.generated_videos[0].video
        ):
            video = operation.result.generated_videos[0].video

            # Calculate cost based on model and resolution
            price_per_second = get_price_per_second(model_name, resolution)
            cost = price_per_second * effective_duration

            # Get video bytes - SDK may use different attribute names
            # Try both camelCase and snake_case
            video_bytes = (
                getattr(video, 'videoBytes', None) or
                getattr(video, 'video_bytes', None)
            )

            # If no direct bytes, try to download from URI
            if not video_bytes:
                video_uri = getattr(video, 'uri', None)
                if video_uri:
                    video_bytes = await self._download_video(video_uri)

            if not video_bytes:
                # Log video object attributes for debugging
                video_attrs = {k: type(v).__name__ for k, v in vars(video).items() if not k.startswith('_')}
                raise RuntimeError(f"Video generation succeeded but no video data returned. Video attrs: {video_attrs}")

            # Upload to GCS and get public URL
            public_url, storage_path, file_name, video_size = await self._upload_video(
                video_bytes, user_id
            )

            # Get mime type - try both naming conventions
            mime_type = (
                getattr(video, 'mimeType', None) or
                getattr(video, 'mime_type', None) or
                "video/mp4"
            )

            return VideoGenerationResult(
                url=public_url,
                mime_type=mime_type,
                size=video_size,
                cost=cost,
                storage_path=storage_path,
                file_name=file_name,
            )
        else:
            # Handle generation failure
            return VideoGenerationResult(
                url=None,
                mime_type=None,
                size=0,
                cost=0,
                storage_path=None,
                file_name=None,
            )

    async def _download_video(self, uri: str) -> bytes:
        """Download video from GCS URI or HTTPS URL."""
        if uri.startswith("gs://"):
            # Download from GCS
            bucket_name, blob_name = uri.replace("gs://", "").split("/", 1)

            def _download_sync() -> bytes:
                client = storage.Client()
                blob = client.bucket(bucket_name).blob(blob_name)
                return blob.download_as_bytes()

            return await anyio.to_thread.run_sync(_download_sync)

        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(uri)
            response.raise_for_status()
            return response.content

    async def _url_to_image(self, url: str) -> types.Image:
        """Convert URL to types.Image for Veo API.

        - For gs:// URIs: use gcsUri parameter directly
        - For https:// URLs: download and use imageBytes
        """
        if url.startswith("gs://"):
            return types.Image(gcsUri=url, mimeType="image/png")

        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return types.Image(imageBytes=response.content, mimeType="image/png")

    async def _upload_video(
        self, video_bytes: bytes, user_id: uuid.UUID
    ) -> tuple[str, str, str, int]:
        """
        Upload video bytes to GCS and return (public_url, storage_path, file_name, size).
        """
        video_size = len(video_bytes)
        file_id = str(uuid.uuid4())
        file_name = f"video-{file_id[:8]}.mp4"
        blob_name = path_resolver.user_file(user_id, "video", f"video-{file_id[:8]}", "mp4")

        if self.bucket:
            # Upload to GCS
            def _upload_sync() -> str:
                blob = self.bucket.blob(blob_name)
                blob.cache_control = "public, max-age=31536000"
                blob.upload_from_file(BytesIO(video_bytes), content_type="video/mp4")
                # Return public URL
                if self.custom_domain:
                    return f"https://{self.custom_domain}/{blob_name}"
                return f"https://storage.googleapis.com/{self.output_bucket}/{blob_name}"

            public_url = await anyio.to_thread.run_sync(_upload_sync)
        else:
            # No GCS configured - this shouldn't happen in production
            raise RuntimeError("GCS bucket not configured for video storage")

        return public_url, blob_name, file_name, video_size
