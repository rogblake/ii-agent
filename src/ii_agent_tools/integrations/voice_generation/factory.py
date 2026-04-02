from ii_agent_tools.integrations.voice_generation.base import BaseVoiceGenerationClient
from ii_agent_tools.integrations.voice_generation.config import VoiceGenerateConfig
from ii_agent_tools.integrations.voice_generation.constants import (
    VoiceGenerationProvider,
    PROVIDER_ALIASES,
)
from ii_agent_tools.integrations.voice_generation.registry import (
    get_provider,
    list_providers,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


def create_voice_generation_client(
    settings: VoiceGenerateConfig,
    model_name: str | None = None,
    provider: str | None = None,
) -> BaseVoiceGenerationClient:
    if provider in PROVIDER_ALIASES:
        provider = PROVIDER_ALIASES[provider].value

    if provider:
        provider_class = get_provider(provider)
        if provider_class is None:
            available = list_providers()
            raise ValueError(f"Unknown provider '{provider}'. Available providers: {available}")
        return _create_client(provider, provider_class, settings, model_name)

    if settings.elevenlabs_api_key:
        logger.info("Using ElevenLabs for voice generation")
        provider_class = get_provider(VoiceGenerationProvider.ELEVENLABS.value)
        return _create_client(
            VoiceGenerationProvider.ELEVENLABS.value,
            provider_class,
            settings,
            model_name,
        )

    if settings.has_gemini_tts_credentials():
        logger.info("Using Gemini TTS for voice generation")
        provider_class = get_provider(VoiceGenerationProvider.GEMINI.value)
        return _create_client(
            VoiceGenerationProvider.GEMINI.value,
            provider_class,
            settings,
            model_name,
        )

    if settings.fal_api_key:
        logger.info("Using fal for voice generation")
        provider_class = get_provider(VoiceGenerationProvider.FAL.value)
        return _create_client(
            VoiceGenerationProvider.FAL.value,
            provider_class,
            settings,
            model_name,
        )

    raise ValueError("No voice generation provider configured")


def _create_client(
    provider: str,
    provider_class: type[BaseVoiceGenerationClient],
    settings: VoiceGenerateConfig,
    model_name: str | None,
) -> BaseVoiceGenerationClient:
    if provider == VoiceGenerationProvider.ELEVENLABS.value:
        return provider_class(
            api_key=settings.elevenlabs_api_key,
            base_url=settings.elevenlabs_base_url,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
            default_voice_id=settings.elevenlabs_default_voice_id,
            voice_id_by_language=settings.get_elevenlabs_voice_id_map(),
            model_name=model_name or settings.elevenlabs_model,
        )
    if provider == VoiceGenerationProvider.GEMINI.value:
        return provider_class(
            api_key=settings.google_ai_studio_api_key,
            project_id=settings.gcp_project_id,
            location=settings.gcp_location,
            output_bucket=settings.gcs_output_bucket,
            default_voice_name=settings.gemini_default_voice_name,
            voice_name_by_language=settings.get_gemini_voice_name_map(),
            model_name=model_name or settings.gemini_model_name,
        )
    if provider == VoiceGenerationProvider.FAL.value:
        return provider_class(
            api_key=settings.fal_api_key,
            model_name=model_name or settings.fal_model_name,
            request_mode=settings.fal_request_mode,
        )
    return provider_class()
