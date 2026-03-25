from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel


class VideoReferenceImage(BaseModel):
    """Reference image for video generation (Veo 3.1+).

    The reference_type should be "asset" according to Google API documentation.
    See: https://ai.google.dev/gemini-api/docs/video#reference-images

    url: Public HTTPS URL or GCS URI (gs://)
    """

    url: str | None = None
    reference_type: Literal["asset"] = "asset"


class VideoGenerationResult(BaseModel):
    url: str | None = None
    mime_type: str | None = None
    size: int | None = None
    cost: float = 0.0
    search_results: list[dict[str, Any]] | None = None
    storage_path: str | None = None
    file_name: str | None = None
    error: str | None = None


class BaseVideoGenerationClient(ABC):
    """Base interface for video generation clients."""

    supports_long_generation: bool = True

    @abstractmethod
    def __init__(self, **kwargs):
        """Initialize the client with provider-specific configuration."""
        pass

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        model_name: str,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] = "16:9",
        duration_seconds: int = 5,
        resolution: str = "720p",
        audio_included: bool = False,
        # Frame URLs (passed directly to Veo API)
        start_frame: str | None = None,
        end_frame: str | None = None,
        # Veo 3.1 additional parameters
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list["VideoReferenceImage"] | None = None,
        **kwargs,
    ) -> VideoGenerationResult:
        """Generate video from text prompt or/and image.

        Args:
            prompt: Text description of the video to generate
            model_name: Model identifier (e.g., "veo-3.1-generate-preview")
            aspect_ratio: Video aspect ratio ("16:9" or "9:16")
            duration_seconds: Duration in seconds (4, 6, or 8)
            resolution: Video resolution ("720p", "1080p", "4k")
            audio_included: Whether to generate audio with the video
            start_frame: URL of start frame image (https:// or gs://)
            end_frame: URL of end frame image (https:// or gs://)
            negative_prompt: Description of unwanted content
            person_generation: Person generation mode ("allow_all" or "allow_adult")
            seed: Random seed for reproducibility
            reference_images: List of reference images for style/content (Veo 3.1+)
        """
        pass

    async def extend_video(
        self,
        video_uri: str,
        prompt: str,
        extension_seconds: int = 7,
        generate_audio: bool = True,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        end_frame: str | None = None,
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

        Note: Not all implementations support video extension.
        """
        raise NotImplementedError("Video extension not supported by this client")
