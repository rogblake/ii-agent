from ii_agent_tools.integrations.image_generation.base import BaseImageGenerationClient
from ii_agent_tools.integrations.image_generation.config import ImageGenerateConfig
from ii_agent_tools.integrations.fal_ai import is_fal_provider_or_model
from .registry import get_provider, list_providers
from .constants import ImageGenerationProvider, PROVIDER_ALIASES
from ii_agent_tools.logger import get_logger


logger = get_logger(__name__)


def create_image_generation_client(
    settings: ImageGenerateConfig,
    model_name: str | None = None,
    provider: str | None = None,
) -> BaseImageGenerationClient:
    normalized_provider = _normalize_provider(provider)
    resolved_model_name = _resolve_model_name(settings, model_name, normalized_provider)
    resolved_provider = _resolve_provider(
        settings,
        provider=normalized_provider,
        model_name=resolved_model_name,
    )
    provider_class = get_provider(resolved_provider)
    if provider_class is None:
        available = list_providers()
        raise ValueError(
            f"Unknown provider '{resolved_provider}'. Available providers: {available}"
        )

    return _create_client(
        resolved_provider,
        provider_class,
        settings,
        resolved_model_name,
    )


def _create_client(
    provider: str,
    provider_class: type[BaseImageGenerationClient],
    settings: ImageGenerateConfig,
    model_name: str | None,
) -> BaseImageGenerationClient:
    """Create a client instance based on provider type."""
    if provider == ImageGenerationProvider.GEMINI.value:
        return provider_class(
            api_key=settings.get_gemini_api_key(),
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
            model_name=model_name or settings.gemini_model_name,
        )
    if provider == ImageGenerationProvider.VERTEX.value:
        return provider_class(
            project_id=settings.gcp_project_id,
            location=settings.gcp_location,
            output_bucket=settings.gcs_output_bucket,
            model_name=model_name,
        )
    if provider == ImageGenerationProvider.OPENAI.value:
        return provider_class(
            api_key=settings.openai_api_key,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
            model_name=model_name,
        )
    if provider == ImageGenerationProvider.FAL.value:
        return provider_class(
            api_key=settings.fal_api_key,
            model_name=model_name or settings.fal_model_name,
            request_mode=settings.fal_request_mode,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
        )
    return provider_class()


def _normalize_provider(provider: str | None) -> str | None:
    if provider is None:
        return None

    normalized = provider.strip().lower()
    if normalized in PROVIDER_ALIASES:
        return PROVIDER_ALIASES[normalized].value
    return normalized


def _resolve_model_name(
    settings: ImageGenerateConfig,
    model_name: str | None,
    provider: str | None,
) -> str | None:
    if model_name:
        return model_name
    if provider == ImageGenerationProvider.GEMINI.value:
        return settings.gemini_model_name
    return None


def _resolve_provider(
    settings: ImageGenerateConfig,
    *,
    provider: str | None,
    model_name: str | None,
) -> str:
    if provider == ImageGenerationProvider.GEMINI.value:
        if _is_imagen_model(model_name):
            if settings.gcp_project_id and settings.gcp_location:
                logger.info("Using Vertex AI for Imagen image generation")
                return ImageGenerationProvider.VERTEX.value
            raise ValueError(
                "Imagen image generation requires Vertex AI configuration"
            )

        if settings.has_gemini_api_key():
            logger.info("Using Gemini API key for image generation")
            return ImageGenerationProvider.GEMINI.value

        if settings.gcp_project_id and settings.gcp_location:
            logger.info("Using Vertex AI for image generation (Gemini fallback)")
            return ImageGenerationProvider.VERTEX.value

        raise ValueError(
            "Gemini image generation requires GEMINI_API_KEY or Vertex AI configuration"
        )

    if provider:
        return provider

    if _is_openai_model(model_name):
        if not settings.openai_api_key:
            raise ValueError("OpenAI image generation requires openai_api_key")
        logger.info("Using OpenAI for image generation")
        return ImageGenerationProvider.OPENAI.value

    if is_fal_provider_or_model(None, model_name):
        if not settings.fal_api_key:
            raise ValueError("fal image generation requires fal_api_key")
        logger.info("Using fal for image generation")
        return ImageGenerationProvider.FAL.value

    if _is_imagen_model(model_name):
        if not (settings.gcp_project_id and settings.gcp_location):
            raise ValueError(
                "Imagen image generation requires Vertex AI configuration"
            )
        logger.info("Using Vertex AI for Imagen image generation")
        return ImageGenerationProvider.VERTEX.value

    if _is_gemini_model(model_name):
        if settings.has_gemini_api_key():
            logger.info("Using Gemini API key for image generation")
            return ImageGenerationProvider.GEMINI.value

        if settings.gcp_project_id and settings.gcp_location:
            logger.info("Using Vertex AI for Gemini image generation")
            return ImageGenerationProvider.VERTEX.value

        raise ValueError(
            "Gemini image generation requires GEMINI_API_KEY or Vertex AI configuration"
        )

    if settings.has_gemini_api_key():
        logger.info("Using Gemini API key for image generation")
        return ImageGenerationProvider.GEMINI.value

    if settings.gcp_project_id and settings.gcp_location:
        logger.info("Using Vertex AI for image generation")
        return ImageGenerationProvider.VERTEX.value

    if settings.fal_api_key:
        logger.info("Using fal for image generation")
        return ImageGenerationProvider.FAL.value

    logger.info("Falling back to DuckDuckGo image search for image generation")
    return ImageGenerationProvider.DUCKDUCKGO.value


def _is_imagen_model(model_name: str | None) -> bool:
    if not model_name:
        return False
    return model_name.startswith("imagen")


def _is_gemini_model(model_name: str | None) -> bool:
    if not model_name:
        return False
    return model_name.startswith("gemini-")


def _is_openai_model(model_name: str | None) -> bool:
    if not model_name:
        return False
    return model_name.startswith("gpt-image")
