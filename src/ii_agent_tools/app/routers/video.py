from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ii_agent_tools.app.deps import (
    get_video_generation_service,
    verify_api_key,
)
from ii_agent_tools.integrations.video_generation.base import VideoReferenceImage
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["video"])


class VideoGenerationRequest(BaseModel):
    prompt: str
    model_name: str | None = Field(default=None, description="Model identifier")
    provider: str = Field(default="vertex", description="Provider name")
    aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] = "16:9"
    duration_seconds: int = Field(..., ge=3, le=30)
    resolution: Literal["480p", "720p", "1080p", "4k"] = Field(
        default="720p",
        description="Video resolution (480p, 720p, 1080p, or 4k)"
    )
    audio_included: bool = Field(default=True, description="Whether to generate audio")
    multishot_mode: bool = Field(
        default=True,
        description="Whether to use multishot mode when supported"
    )
    # Frame URLs (https:// or gs://) passed directly to Veo API
    start_frame: str | None = None
    end_frame: str | None = None
    # Veo 3.1 additional parameters
    negative_prompt: str | None = Field(default=None, description="What to exclude from video")
    person_generation: Literal["allow_all", "allow_adult"] | None = Field(
        default=None,
        description="Person generation mode"
    )
    seed: int | None = Field(default=None, description="Random seed for reproducibility")
    reference_images: list[VideoReferenceImage] | None = Field(
        default=None,
        description="Optional Veo 3.1 reference images (up to 3 asset images).",
    )
    # Extension API for long videos
    use_extension_api: bool = Field(
        default=True,
        description="Use extension API for long videos (maintains audio coherence)"
    )
    provider_payload: Dict[str, Any] | None = None
    request_mode: str | None = None


class VideoExtensionRequest(BaseModel):
    """Request to extend an existing video using Veo's extension API."""
    source_video_url: str = Field(
        ...,
        description="URL of the video to extend. Can be HTTP(S) URL or GCS URI."
    )
    prompt: str = Field(
        ...,
        description="Text prompt describing how the video should continue."
    )
    extension_seconds: int = Field(
        default=7,
        ge=1,
        le=7,
        description="Duration to extend by (max 7s per call)."
    )
    generate_audio: bool = Field(
        default=True,
        description="Whether to continue generating synchronized audio."
    )
    person_generation: Literal["allow_all", "allow_adult"] | None = Field(
        default=None,
        description="Person generation mode."
    )
    end_frame: str | None = Field(
        default=None,
        description="URL of end frame image (https:// or gs://)."
    )


class VideoGenerationResponse(BaseModel):
    success: bool
    url: str | None = None
    size: int | None = None
    mime_type: str | None = None
    error: str | None = None
    search_results: List[Dict[str, Any]] | None = None
    cost: float | None = None
    storage_path: str | None = None


@router.post("/video-generation", response_model=VideoGenerationResponse)
async def video_generation(
    request: VideoGenerationRequest,
    auth: dict = Depends(verify_api_key),
    video_service=Depends(get_video_generation_service),
):
    """Generate video from text prompt or/and image."""

    try:
        video_result = await video_service.generate_video(
            prompt=request.prompt,
            model_name=request.model_name,
            provider=request.provider,
            aspect_ratio=request.aspect_ratio,
            duration_seconds=request.duration_seconds,
            resolution=request.resolution,
            audio_included=request.audio_included,
            multishot_mode=request.multishot_mode,
            start_frame=request.start_frame,
            end_frame=request.end_frame,
            negative_prompt=request.negative_prompt,
            person_generation=request.person_generation,
            seed=request.seed,
            reference_images=request.reference_images,
            use_extension_api=request.use_extension_api,
            provider_payload=request.provider_payload,
            request_mode=request.request_mode,
        )
    except ValueError as e:
        logger.error("Video generation validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to generate video",
            extra={
                "prompt": request.prompt,
                "duration_seconds": request.duration_seconds,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to generate video")

    if video_result.error:
        return VideoGenerationResponse(success=False, error=video_result.error)

    response = VideoGenerationResponse(
        success=True,
        url=video_result.url,
        size=video_result.size,
        mime_type=video_result.mime_type,
        search_results=video_result.search_results,
        cost=video_result.cost,
        storage_path=video_result.storage_path,
    )

    return response


@router.post("/video-extension", response_model=VideoGenerationResponse)
async def video_extension(
    request: VideoExtensionRequest,
    auth: dict = Depends(verify_api_key),
    video_service=Depends(get_video_generation_service),
):
    """
    Extend an existing video using Veo's video extension API.

    Returns a merged video (original + extension) with maintained audio/visual coherence.
    Max 7 seconds per call, can be repeated up to 20 times (~148s total).
    """
    try:
        video_result = await video_service.extend_video(
            source_video_url=request.source_video_url,
            prompt=request.prompt,
            extension_seconds=request.extension_seconds,
            generate_audio=request.generate_audio,
            person_generation=request.person_generation,
            end_frame=request.end_frame,
        )
    except ValueError as e:
        logger.error("Video extension validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to extend video",
            extra={
                "source_video_url": request.source_video_url[:100],
                "extension_seconds": request.extension_seconds,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to extend video")

    if video_result.error:
        return VideoGenerationResponse(success=False, error=video_result.error)

    return VideoGenerationResponse(
        success=True,
        url=video_result.url,
        size=video_result.size,
        mime_type=video_result.mime_type,
        cost=video_result.cost,
        storage_path=video_result.storage_path,
    )
