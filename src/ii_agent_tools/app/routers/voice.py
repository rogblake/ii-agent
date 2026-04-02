from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ii_agent_tools.app.deps import get_voice_generation_service, verify_api_key
from ii_agent_tools.logger import get_logger

router = APIRouter(tags=["voice"])
logger = get_logger(__name__)


class VoiceGenerationRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    voice_id: str | None = Field(
        default=None, description="Provider-specific voice identifier"
    )
    provider: str | None = None
    model_name: str | None = Field(default=None, description="Provider model identifier")
    output_format: str = Field(
        default="mp3_44100_128", description="Output audio format"
    )
    voice_settings: Dict[str, Any] | None = None
    language_code: str | None = None
    seed: int | None = None
    provider_payload: Dict[str, Any] | None = None
    request_mode: str | None = None
    pronunciation_dictionary_locators: List[Dict[str, Any]] | None = None
    previous_text: str | None = None
    next_text: str | None = None
    previous_request_ids: List[str] | None = None
    next_request_ids: List[str] | None = None
    enable_logging: bool | None = None
    optimize_streaming_latency: int | None = None
    apply_text_normalization: str | None = None
    apply_language_text_normalization: str | None = None


class VoiceGenerationResponse(BaseModel):
    success: bool
    url: str | None = None
    size: int | None = None
    mime_type: str | None = None
    error: str | None = None
    cost: float | None = None
    storage_path: str | None = None
    file_name: str | None = None


@router.post("/voice-generation", response_model=VoiceGenerationResponse)
async def voice_generation(
    request: VoiceGenerationRequest,
    auth: dict = Depends(verify_api_key),
    voice_service=Depends(get_voice_generation_service),
):
    """Generate voice audio from text using configured providers."""
    try:
        result = await voice_service.generate_voice(
            text=request.text,
            voice_id=request.voice_id,
            provider=request.provider,
            model_name=request.model_name,
            output_format=request.output_format,
            voice_settings=request.voice_settings,
            language_code=request.language_code,
            seed=request.seed,
            provider_payload=request.provider_payload,
            request_mode=request.request_mode,
            pronunciation_dictionary_locators=request.pronunciation_dictionary_locators,
            previous_text=request.previous_text,
            next_text=request.next_text,
            previous_request_ids=request.previous_request_ids,
            next_request_ids=request.next_request_ids,
            enable_logging=request.enable_logging,
            optimize_streaming_latency=request.optimize_streaming_latency,
            apply_text_normalization=request.apply_text_normalization,
            apply_language_text_normalization=request.apply_language_text_normalization,
        )
    except ValueError as e:
        logger.error("Voice generation validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to generate voice",
            extra={
                "voice_id": request.voice_id,
                "provider": request.provider,
                "model_name": request.model_name,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to generate voice")

    return VoiceGenerationResponse(
        success=True,
        url=result.url,
        size=result.size,
        mime_type=result.mime_type,
        cost=result.cost,
        storage_path=result.storage_path,
        file_name=result.file_name,
    )
