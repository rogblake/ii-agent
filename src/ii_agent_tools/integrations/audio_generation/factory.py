from ii_agent_tools.integrations.audio_generation.base import BaseAudioGenerationClient
from ii_agent_tools.integrations.audio_generation.config import AudioGenerateConfig
from ii_agent_tools.integrations.audio_generation.constants import (
    AudioGenerationProvider,
    PROVIDER_ALIASES,
)
from ii_agent_tools.integrations.audio_generation.registry import (
    get_provider,
    list_providers,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


def create_audio_generation_client(
    settings: AudioGenerateConfig,
    model_name: str | None = None,
    provider: str | None = None,
) -> BaseAudioGenerationClient:
    if provider in PROVIDER_ALIASES:
        provider = PROVIDER_ALIASES[provider].value

    if provider:
        provider_class = get_provider(provider)
        if provider_class is None:
            available = list_providers()
            raise ValueError(
                f"Unknown provider '{provider}'. Available providers: {available}"
            )
        return _create_client(provider, provider_class, settings, model_name)

    if settings.fal_api_key:
        logger.info("Using fal for audio generation")
        provider_class = get_provider(AudioGenerationProvider.FAL.value)
        return _create_client(
            AudioGenerationProvider.FAL.value,
            provider_class,
            settings,
            model_name,
        )

    raise ValueError("No audio generation provider configured")


def _create_client(
    provider: str,
    provider_class: type[BaseAudioGenerationClient],
    settings: AudioGenerateConfig,
    model_name: str | None,
) -> BaseAudioGenerationClient:
    if provider == AudioGenerationProvider.FAL.value:
        return provider_class(
            api_key=settings.fal_api_key,
            model_name=model_name or settings.fal_model_name,
            request_mode=settings.fal_request_mode,
        )
    return provider_class()
