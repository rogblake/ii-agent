from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ii_agent_tools.app.deps import get_audio_generation_service, verify_api_key
from ii_agent_tools.logger import get_logger

router = APIRouter(tags=["audio"])
logger = get_logger(__name__)


class AudioGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt for audio/music generation")
    provider: str | None = Field(default=None, description="Provider name")
    model_name: str | None = Field(default=None, description="Provider model identifier")
    music_length_ms: int | None = Field(default=None, ge=1000)
    force_instrumental: bool | None = None
    output_format: str | None = None
    seed: int | None = Field(default=None, ge=0)
    provider_payload: Dict[str, Any] | None = None
    request_mode: str | None = None


class AudioGenerationResponse(BaseModel):
    success: bool
    url: str | None = None
    size: int | None = None
    mime_type: str | None = None
    error: str | None = None
    cost: float | None = None
    storage_path: str | None = None
    file_name: str | None = None


@router.post("/audio-generation", response_model=AudioGenerationResponse)
async def audio_generation(
    request: AudioGenerationRequest,
    auth: dict = Depends(verify_api_key),
    audio_service=Depends(get_audio_generation_service),
):
    """Generate audio/music using configured providers."""
    try:
        result = await audio_service.generate_audio(
            prompt=request.prompt,
            provider=request.provider,
            model_name=request.model_name,
            music_length_ms=request.music_length_ms,
            force_instrumental=request.force_instrumental,
            output_format=request.output_format,
            seed=request.seed,
            provider_payload=request.provider_payload,
            request_mode=request.request_mode,
        )
    except ValueError as e:
        logger.error("Audio generation validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to generate audio",
            extra={
                "provider": request.provider,
                "model_name": request.model_name,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to generate audio")

    return AudioGenerationResponse(
        success=True,
        url=result.url,
        size=result.size,
        mime_type=result.mime_type,
        cost=result.cost,
        storage_path=result.storage_path,
        file_name=result.file_name,
    )
