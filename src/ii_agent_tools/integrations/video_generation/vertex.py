import asyncio
import uuid
from io import BytesIO
from typing import Any, Literal

import anyio
import httpx
from google import genai
from google.cloud import storage
from google.genai import types

from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent_tools.logger import get_logger

from .base import BaseVideoGenerationClient, VideoGenerationResult, VideoReferenceImage

logger = get_logger(__name__)

# Model name mapping from frontend model IDs to Veo API model names
VEO_MODELS = {
    "veo-3.1-premium": "veo-3.1-generate-preview",  # Supports reference images
    "veo-3.1": "veo-3.1-generate-preview",  # Supports reference images
    "veo-3.1-preview": "veo-3.1-generate-preview",  # Supports reference images
    "veo-3.1-fast": "veo-3.1-fast-generate-001",
    "veo-3.0": "veo-3.0-generate-001",
    "veo-3.0-fast": "veo-3.0-fast-generate-001",
    "veo-2.0": "veo-2.0-generate-001",
}

DEFAULT_MODEL = "veo-3.1-generate-preview"

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


def _extract_error_message(error: Any) -> str | None:
    """Extract error message from various error object formats."""
    if not error:
        return None
    if isinstance(error, dict):
        return error.get("message")
    if hasattr(error, "message"):
        return error.message
    return str(error)


class VertexVideoGenerationClient(BaseVideoGenerationClient):
    """Vertex AI implementation of video generation client using Veo models."""

    supports_long_generation: bool = True
    supports_extension_api: bool = True
    supports_audio: bool = True
    supports_end_frame: bool = True

    def __init__(
        self,
        project_id: str,
        location: str,
        output_bucket: str | None = None,
        result_expiration_seconds: int = 3600,
        blob_name_prefix: str = "video_generation",
        custom_domain: str | None = None,
    ):
        """
        Initialize Vertex AI client for video generation.

        Args:
            project_id: GCP project ID
            location: GCP location/region
            output_bucket: GCS bucket to store generated videos
            result_expiration_seconds: Expiration time for signed URLs
            blob_name_prefix: Prefix for blob storage path
            custom_domain: Custom domain for public URLs (e.g., sfile.ii.inc)
        """
        self.project_id = project_id
        self.location = location
        self.output_bucket = output_bucket
        self.custom_domain = custom_domain
        self.client = genai.Client(
            project=project_id,
            location=location,
            vertexai=True,
        )
        # Resolve model name from frontend ID to API model name
        self.bucket = storage.Client(project=project_id).bucket(output_bucket)
        self.result_expiration_seconds = result_expiration_seconds
        self.blob_name_prefix = blob_name_prefix

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
        # Veo 3.1 additional parameters
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list[VideoReferenceImage] | None = None,
        user_id: uuid.UUID | None = None,
        **kwargs,
    ) -> VideoGenerationResult:
        """
        Generate video from text prompt and/or reference frames.

        Supports Veo 3.1 features:
        - Native audio generation
        - Start frame (image-to-video)
        - End frame (frame interpolation)
        - Resolution control (720p, 1080p for 8s videos)
        - Negative prompt (what to exclude)
        - Person generation mode
        - Seed for reproducibility
        - Reference images for style/content guidance

        Args:
            start_frame: URL of start frame image (https:// or gs://)
            end_frame: URL of end frame image (https:// or gs://)
        """
        model_name = self._resolve_model_name(model_name)

        # Prepare start frame (image) if provided
        start_image = None
        if start_frame:
            start_image = await self._url_to_image(start_frame)
            logger.info(f"[VertexVideoGeneration] Using start_frame: {start_frame}")

        # Prepare end frame (lastFrame) if provided - Veo 3.1 feature
        end_image = None
        if end_frame:
            end_image = await self._url_to_image(end_frame)
            logger.info(f"[VertexVideoGeneration] Using end_frame: {end_frame}")

        # Build generation config using camelCase parameter names for SDK
        # NOTE: We do NOT set outputGcsUri here because the bucket has uniform
        # bucket-level access enabled, which causes ACL errors when Veo tries
        # to write directly. Instead, we'll download from Veo's temp storage
        # and upload to our GCS ourselves.
        effective_duration = min(duration_seconds, 8)  # Veo max is 8s

        logger.info(
            f"[VertexVideoGeneration] Config: duration_seconds={duration_seconds}, "
            f"effective_duration={effective_duration}, resolution={resolution}, "
            f"aspect_ratio={aspect_ratio}, audio={audio_included}"
        )

        config_kwargs = {
            "aspectRatio": aspect_ratio,
            "numberOfVideos": 1,
            "durationSeconds": effective_duration,
        }

        # Only pass resolution for pure text-to-video (no image/video reference)
        # When there's reference input, API infers resolution from the source
        has_reference = start_frame or end_frame or reference_images
        if not has_reference and resolution in ("720p", "1080p", "4k"):
            config_kwargs["resolution"] = resolution

        # Add audio generation for Veo 3.x models
        if audio_included and "veo-3" in model_name:
            config_kwargs["generateAudio"] = True

        # Add end frame (last frame) if provided - Veo 3.1 feature
        if end_image and "veo-3.1" in model_name:
            config_kwargs["lastFrame"] = end_image

        # Add negative prompt if provided
        if negative_prompt:
            config_kwargs["negativePrompt"] = negative_prompt

        # Add person generation mode if provided
        if person_generation:
            # Map to SDK enum value
            person_gen_map = {
                "allow_all": "ALLOW_ALL",
                "allow_adult": "ALLOW_ADULT",
            }
           # config_kwargs["personGeneration"] = person_gen_map.get(
           #     person_generation, "ALLOW_ALL"
           # )

        # Add seed for reproducibility (Veo 3.x only)
        if seed is not None and "veo-3" in model_name:
            config_kwargs["seed"] = seed

        # Add reference images for style/content guidance (Veo 3.1 only)
        if reference_images and "veo-3.1" in model_name:
            ref_images_list = []
            for ref_img in reference_images:
                if not ref_img.url:
                    logger.warning("[VertexVideoGeneration] Skipping reference image with no URL")
                    continue
                # Convert URL to types.Image (handles both gs:// and https://)
                image = await self._url_to_image(ref_img.url)

                ref_image = types.VideoGenerationReferenceImage(
                    image=image,
                    referenceType=ref_img.reference_type,
                )
                ref_images_list.append(ref_image)
            if ref_images_list:
                config_kwargs["referenceImages"] = ref_images_list
                logger.info(f"[VertexVideoGeneration] Using {len(ref_images_list)} reference images")

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

        logger.debug(f"[VertexVideoGeneration] Operation started, done={operation.done}")

        # Poll for completion - pass the operation OBJECT (not name) to operations.get()
        polling_interval_seconds = 5
        max_wait_time_seconds = 360  # 6 minutes
        elapsed_time = 0

        # Handle done=None or done=False - both mean not complete
        while operation.done is not True:
            if elapsed_time >= max_wait_time_seconds:
                raise TimeoutError(f"Video generation timed out after {max_wait_time_seconds} seconds")
            await asyncio.sleep(polling_interval_seconds)
            elapsed_time += polling_interval_seconds
            logger.debug(f"[VertexVideoGeneration] Polling... (elapsed: {elapsed_time}s)")
            # Pass the operation OBJECT, not the name string!
            operation = self.client.operations.get(operation=operation)
            logger.debug(f"[VertexVideoGeneration] Poll result: done={operation.done}")

        logger.debug(f"[VertexVideoGeneration] Polling complete! Final done={operation.done}")

        # Process result
        if (
            operation.result
            and operation.result.generated_videos
            and operation.result.generated_videos[0].video
        ):
            video = operation.result.generated_videos[0].video

            # Calculate cost based on model and resolution
            price_per_second = get_price_per_second(model_name, resolution)
            cost = price_per_second * duration_seconds

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

            # Upload video to GCS
            public_url, storage_path, file_name, video_size = await self._upload_video(
                video_bytes, user_id
            )

            return VideoGenerationResult(
                url=public_url,
                mime_type="video/mp4",
                size=video_size,
                cost=cost,
                storage_path=storage_path,
                file_name=file_name,
            )
        # Handle generation failure
        error_msg = _extract_error_message(getattr(operation, "error", None))
        if not error_msg:
            error_msg = "Video generation failed. This could be due to content policy violation or service error."

        return VideoGenerationResult(
            url=None,
            mime_type=None,
            size=0,
            cost=0,
            error=error_msg,
        )

    async def extend_video(
        self,
        video_uri: str,
        prompt: str,
        extension_seconds: int = 7,
        generate_audio: bool = True,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        end_frame: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> VideoGenerationResult:
        """Extend existing video while maintaining audio/visual coherence.

        This uses Veo's video extension API which maintains visual and audio
        coherence across multiple extensions (up to ~148 seconds total).

        Args:
            video_uri: GCS URI of the video to extend (gs://bucket/path)
            prompt: Text prompt for the extension
            extension_seconds: Duration to extend by (default 7s, max 7s per step)
            generate_audio: Whether to continue generating audio
            person_generation: Person generation mode ("allow_all" or "allow_adult")
            end_frame: URL of end frame image (https:// or gs://)

        Returns:
            VideoGenerationResult with extended video
        """
        # Ensure extension is within valid range (max 7s per step)
        extension_seconds = min(extension_seconds, 7)

        # Use default Veo 3.1 preview model for extension
        model_name = "veo-3.1-generate-preview"

        # If end_frame is provided, use frame interpolation instead of extension
        # Extension API doesn't support end_frame, but frame interpolation does
        if end_frame:
            logger.info(
                "[VertexVideoGeneration] end_frame provided - using frame interpolation instead of extension"
            )
            # Extract last frame from source video and use frame interpolation
            start_frame_from_video = await self._extract_last_frame_from_video(video_uri, user_id=user_id)
            if start_frame_from_video:
                # Generate final segment with frame interpolation
                final_segment = await self.generate_video(
                    prompt=prompt,
                    model_name=model_name,
                    aspect_ratio="16:9",  # Frame interpolation requires 16:9
                    duration_seconds=8,    # Frame interpolation requires 8s
                    audio_included=generate_audio,
                    start_frame=start_frame_from_video,
                    end_frame=end_frame,
                    person_generation=person_generation,
                    user_id=user_id,
                )

                if final_segment.url:
                    # Concatenate source video + final segment
                    concatenated = await self._concatenate_videos(video_uri, final_segment.url, user_id=user_id)
                    if concatenated:
                        return concatenated
                    else:
                        logger.warning(
                            "[VertexVideoGeneration] Failed to concatenate - returning final segment only"
                        )
                return final_segment
            else:
                logger.warning(
                    "[VertexVideoGeneration] Failed to extract frame from video - falling back to extension without end_frame"
                )

        # Generate output path for extended video
        file_id = str(uuid.uuid4())
        output_blob_name = path_resolver.user_file(user_id, "video", f"extended-{file_id[:8]}", "mp4")
        output_gcs_uri = f"gs://{self.output_bucket}/{output_blob_name}"

        # Build config for extension
        config_kwargs = {
            "durationSeconds": extension_seconds,
            "numberOfVideos": 1,
            "outputGcsUri": output_gcs_uri,  # Required for large videos (extensions)
        }

        if generate_audio:
            config_kwargs["generateAudio"] = True

        # Add person generation mode if provided
        if person_generation:
            person_gen_map = {
                "allow_all": "ALLOW_ALL",
                "allow_adult": "ALLOW_ADULT",
            }
            config_kwargs["personGeneration"] = person_gen_map.get(
                person_generation, "ALLOW_ALL"
            )

        config = types.GenerateVideosConfig(**config_kwargs)

        # Create video reference from existing video URI
        # Must specify mimeType for the API to accept the video
        video = types.Video(uri=video_uri, mimeType="video/mp4")

        # Build source with video and prompt
        source = types.GenerateVideosSource(
            video=video,
            prompt=prompt,
        )

        # Submit the extension operation
        operation = await self.client.aio.models.generate_videos(
            model=model_name,
            source=source,
            config=config,
        )

        logger.debug(f"[VertexVideoGeneration] Extension operation started, done={operation.done}")

        # Poll for completion
        polling_interval_seconds = 5
        max_wait_time_seconds = 360
        elapsed_time = 0

        while operation.done is not True:
            if elapsed_time >= max_wait_time_seconds:
                raise TimeoutError(
                    f"Video extension timed out after {max_wait_time_seconds} seconds."
                )
            await asyncio.sleep(polling_interval_seconds)
            elapsed_time += polling_interval_seconds
            logger.debug(f"[VertexVideoGeneration] Extension polling... (elapsed: {elapsed_time}s)")
            operation = self.client.operations.get(operation=operation)

        logger.debug(f"[VertexVideoGeneration] Extension complete! done={operation.done}")

        # Process result
        if (
            operation.result
            and operation.result.generated_videos
            and operation.result.generated_videos[0].video
        ):
            video = operation.result.generated_videos[0].video

            # Calculate cost (extensions are 720p only)
            price_per_second = get_price_per_second(model_name, "720p")
            cost = price_per_second * extension_seconds

            # Try to get video bytes - check if outputGcsUri worked or if we need to download
            video_bytes = None

            # First check if outputGcsUri worked (file exists in our bucket)
            try:
                blob = self.bucket.blob(output_blob_name)
                if blob.exists():
                    video_bytes = blob.download_as_bytes()
                    logger.debug(f"[VertexVideoGeneration] Video found at outputGcsUri: {output_blob_name}, size={len(video_bytes)}")
            except Exception as e:
                logger.debug(f"[VertexVideoGeneration] outputGcsUri file not found or error: {e}")

            # If outputGcsUri didn't work, try to get from video response
            if not video_bytes:
                # Try direct bytes from response
                video_bytes = (
                    getattr(video, 'videoBytes', None) or
                    getattr(video, 'video_bytes', None)
                )

                # If no direct bytes, try to download from URI
                if not video_bytes:
                    video_uri_from_response = getattr(video, 'uri', None)
                    if video_uri_from_response:
                        video_bytes = await self._download_video(video_uri_from_response)

            if not video_bytes:
                return VideoGenerationResult(
                    url=None,
                    mime_type=None,
                    size=0,
                    cost=0,
                    error="Video extension succeeded but no video data returned.",
                )

            # Upload video to GCS (if we downloaded it, or re-upload to ensure it's there)
            public_url, storage_path, file_name, video_size = await self._upload_video(
                video_bytes, user_id
            )

            return VideoGenerationResult(
                url=public_url,
                mime_type="video/mp4",
                size=video_size,
                storage_path=storage_path,
                file_name=file_name,
                cost=cost,
            )
        # Handle extension failure
        error_msg = _extract_error_message(getattr(operation, "error", None))
        return VideoGenerationResult(
            url=None,
            mime_type=None,
            size=0,
            cost=0,
            error=error_msg or "Video extension failed.",
        )

    async def _upload_video(
        self, video_bytes: bytes, user_id: uuid.UUID | None
    ) -> tuple[str, str, str, int]:
        """
        Upload video bytes to GCS.

        Args:
            video_bytes: Video bytes to upload
            user_id: Owner user ID for storage path organization

        Returns:
            Tuple of (public_url, storage_path, file_name, video_size)
        """
        video_size = len(video_bytes)

        # Generate storage path
        file_id = str(uuid.uuid4())
        file_name = f"video-{file_id[:8]}.mp4"
        blob_name = path_resolver.user_file(user_id, "video", f"video-{file_id[:8]}", "mp4")

        # Upload to our GCS bucket
        def _upload_sync() -> str:
            blob = self.bucket.blob(blob_name)
            blob.cache_control = "public, max-age=31536000"
            blob.upload_from_file(BytesIO(video_bytes), content_type="video/mp4")
            # Return public URL - use custom domain if configured
            if self.custom_domain:
                return f"https://{self.custom_domain}/{blob_name}"
            return f"https://storage.googleapis.com/{self.output_bucket}/{blob_name}"

        public_url = await anyio.to_thread.run_sync(_upload_sync)
        return public_url, blob_name, file_name, video_size

    async def _download_video(self, uri: str) -> bytes:
        """Download video from GCS URI or HTTPS URL."""
        if uri.startswith("gs://"):
            bucket_name, blob_name = uri.replace("gs://", "").split("/", 1)

            def _download_sync() -> bytes:
                client = storage.Client(project=self.project_id)
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

    async def _extract_last_frame_from_video(
        self, video_uri: str, *, user_id: uuid.UUID | None = None
    ) -> str | None:
        """Extract the last frame from a video and upload to GCS.

        Args:
            video_uri: GCS URI (gs://) or HTTPS URL of the video
            user_id: Owner user ID for storage path organization

        Returns:
            GCS URI of the extracted frame, or None if extraction failed
        """
        import subprocess
        import tempfile

        try:
            # Download video to temp file
            video_bytes = await self._download_video(video_uri)

            def _write_temp_video() -> str:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_file:
                    video_file.write(video_bytes)
                    return video_file.name

            video_path = await anyio.to_thread.run_sync(_write_temp_video)

            # Extract last frame using ffmpeg
            frame_path = video_path.replace(".mp4", "_last_frame.png")

            # Get video duration first
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]

            def _run_probe():
                result = subprocess.run(probe_cmd, capture_output=True, text=True)
                return float(result.stdout.strip()) if result.returncode == 0 else None

            duration = await anyio.to_thread.run_sync(_run_probe)
            if not duration:
                logger.warning("[VertexVideoGeneration] Failed to get video duration")
                return None

            # Extract frame at duration - 0.1s (to ensure we get a valid frame)
            seek_time = max(0, duration - 0.1)

            extract_cmd = [
                "ffmpeg", "-y",
                "-ss", str(seek_time),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                frame_path
            ]

            def _run_extract():
                result = subprocess.run(extract_cmd, capture_output=True)
                return result.returncode == 0

            success = await anyio.to_thread.run_sync(_run_extract)
            if not success:
                logger.warning("[VertexVideoGeneration] Failed to extract frame from video")
                return None

            # Read frame and upload to GCS
            def _read_and_upload():
                with open(frame_path, "rb") as f:
                    frame_bytes = f.read()

                frame_id = str(uuid.uuid4())[:8]
                blob_name = path_resolver.user_file(user_id, "image", f"frame-{frame_id}", "png")
                blob = self.bucket.blob(blob_name)
                blob.cache_control = "public, max-age=31536000"
                blob.upload_from_file(BytesIO(frame_bytes), content_type="image/png")

                # Clean up temp files
                import os
                os.unlink(video_path)
                os.unlink(frame_path)

                return f"gs://{self.output_bucket}/{blob_name}"

            gcs_uri = await anyio.to_thread.run_sync(_read_and_upload)
            logger.info(f"[VertexVideoGeneration] Extracted last frame to: {gcs_uri}")
            return gcs_uri

        except Exception as e:
            logger.error(f"[VertexVideoGeneration] Failed to extract last frame: {e}")
            return None

    async def _concatenate_videos(
        self, video1_uri: str, video2_uri: str, *, user_id: uuid.UUID | None = None
    ) -> VideoGenerationResult | None:
        """Concatenate two videos using ffmpeg.

        Args:
            video1_uri: GCS URI or URL of the first video
            video2_uri: GCS URI or URL of the second video
            user_id: Owner user ID for storage path organization

        Returns:
            VideoGenerationResult with concatenated video, or None if failed
        """
        import os
        import subprocess
        import tempfile

        try:
            # Download both videos
            video1_bytes = await self._download_video(video1_uri)
            video2_bytes = await self._download_video(video2_uri)

            with tempfile.TemporaryDirectory() as temp_dir:
                video1_path = os.path.join(temp_dir, "video1.mp4")
                video2_path = os.path.join(temp_dir, "video2.mp4")
                output_path = os.path.join(temp_dir, "output.mp4")
                concat_list_path = os.path.join(temp_dir, "concat_list.txt")

                # Write videos to temp files (in thread to avoid blocking)
                def _write_video_files():
                    with open(video1_path, "wb") as f:
                        f.write(video1_bytes)
                    with open(video2_path, "wb") as f:
                        f.write(video2_bytes)
                    with open(concat_list_path, "w") as f:
                        f.write(f"file '{video1_path}'\n")
                        f.write(f"file '{video2_path}'\n")

                await anyio.to_thread.run_sync(_write_video_files)

                # Concatenate using ffmpeg
                concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_list_path,
                    "-c", "copy",
                    output_path
                ]

                def _run_concat():
                    result = subprocess.run(concat_cmd, capture_output=True)
                    return result.returncode == 0

                success = await anyio.to_thread.run_sync(_run_concat)
                if not success:
                    logger.warning("[VertexVideoGeneration] Failed to concatenate videos")
                    return None

                # Read and upload concatenated video
                def _read_and_upload():
                    with open(output_path, "rb") as f:
                        video_bytes = f.read()

                    file_id = str(uuid.uuid4())[:8]
                    blob_name = path_resolver.user_file(user_id, "video", f"concat-{file_id}", "mp4")
                    blob = self.bucket.blob(blob_name)
                    blob.cache_control = "public, max-age=31536000"
                    blob.upload_from_file(BytesIO(video_bytes), content_type="video/mp4")

                    if self.custom_domain:
                        public_url = f"https://{self.custom_domain}/{blob_name}"
                    else:
                        public_url = f"https://storage.googleapis.com/{self.output_bucket}/{blob_name}"

                    return public_url, blob_name, len(video_bytes)

                public_url, storage_path, video_size = await anyio.to_thread.run_sync(
                    _read_and_upload
                )

                logger.info(f"[VertexVideoGeneration] Concatenated video: {public_url}")
                return VideoGenerationResult(
                    url=public_url,
                    storage_path=storage_path,
                    mime_type="video/mp4",
                    size=video_size,
                )

        except Exception as e:
            logger.error(f"[VertexVideoGeneration] Failed to concatenate videos: {e}")
            return None
