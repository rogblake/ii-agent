from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ii_agent_tools.app.deps import (
    get_image_generation_service,
    get_image_search_service,
    verify_api_key,
)
from ii_agent_tools.logger import get_logger

router = APIRouter(tags=["image"])
logger = get_logger(__name__)


class BaseRequest(BaseModel):
    pass


class ImageGenerationRequest(BaseRequest):
    prompt: str
    image_urls: List[str] | None = None
    aspect_ratio: Literal[
        "1:1",
        "2:3",
        "3:2",
        "3:4",
        "4:3",
        "4:5",
        "5:4",
        "9:16",
        "16:9",
        "21:9",
        "1:4",
        "4:1",
        "1:8",
        "8:1",
    ] = "1:1"
    image_size: str = "1K"
    model_name: str | None = None
    provider: str | None = None
    background: Literal["transparent", "opaque", "auto"] | None = None
    provider_payload: Dict[str, Any] | None = None
    request_mode: str | None = None


class ImageGenerationResponse(BaseModel):
    success: bool
    url: str | None = None
    error: str | None = None
    size: int | None = None
    mime_type: str | None = None
    search_results: List[Dict[str, Any]] | None = None
    storage_path: str | None = None
    file_name: str | None = None
    cost: float | None = None
    storage_path: str | None = None
    file_name: str | None = None


@router.post("/image-generation", response_model=ImageGenerationResponse)
async def generate_image(
    request: ImageGenerationRequest,
    auth: dict = Depends(verify_api_key),
    image_service=Depends(get_image_generation_service),
):
    """Generate an image using configured providers (Vertex AI, OpenAI, or DuckDuckGo).

    Supports both text-to-image and image-to-image generation.
    If image_urls is provided, the generated image will be based on both the prompt and reference images.
    The provider can be specified in the request, otherwise it will auto-select based on configuration.
    """
    try:
        result = await image_service.generate_image(
            prompt=request.prompt,
            aspect_ratio=request.aspect_ratio,
            provider=request.provider,
            model_name=request.model_name,
            image_urls=request.image_urls,
            image_size=request.image_size,
            background=request.background,
            provider_payload=request.provider_payload,
            request_mode=request.request_mode,
        )
    except ValueError as e:
        logger.error("Image generation validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to generate image",
            extra={
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio,
                "provider": request.provider,
                "model_name": request.model_name,
                "image_urls": request.image_urls,
                "background": request.background,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to generate image")

    response = ImageGenerationResponse(
        success=True,
        url=result.url,
        size=result.size,
        mime_type=result.mime_type,
        cost=result.cost,
        storage_path=result.storage_path,
        file_name=result.file_name,
    )

    return response


class ImageSearchRequest(BaseRequest):
    query: str
    aspect_ratio: Literal["all", "square", "tall", "wide", "panoramic"] = "all"
    image_type: Literal["all", "face", "photo", "clipart", "lineart", "animated"] = (
        "all"
    )
    min_width: int = 0
    min_height: int = 0
    is_product: bool = False
    max_results: int = 5


class ImageSearchResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]] | None = None
    error: str | None = None
    cost: float | None = None


@router.post("/image-search", response_model=ImageSearchResponse)
async def image_search(
    request: ImageSearchRequest,
    auth: dict = Depends(verify_api_key),
    image_search=Depends(get_image_search_service),
):
    """Perform image search using configured providers."""
    try:
        result = await image_search.search(
            query=request.query,
            aspect_ratio=request.aspect_ratio,
            image_type=request.image_type,
            min_width=request.min_width,
            min_height=request.min_height,
            is_product=request.is_product,
            max_results=request.max_results,
        )
    except Exception:
        logger.exception(
            "Image search failed",
            extra={
                "query": request.query,
                "aspect_ratio": request.aspect_ratio,
                "image_type": request.image_type,
            },
        )
        raise HTTPException(status_code=500, detail="Failed to perform image search")

    return ImageSearchResponse(success=True, results=result.result, cost=result.cost)
