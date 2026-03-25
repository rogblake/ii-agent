from ii_agent_tools.integrations.voice_generation.base import (
    BaseVoiceGenerationClient,
    VoiceGenerationResult,
)
from ii_agent_tools.integrations.voice_generation.config import VoiceGenerateConfig
from ii_agent_tools.integrations.voice_generation.constants import (
    PROVIDER_ALIASES,
    VoiceGenerationProvider,
)
from ii_agent_tools.integrations.voice_generation.factory import (
    create_voice_generation_client,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


class VoiceGenerationService:
    """Voice generation service with provider-per-request support."""

    def __init__(self, config: VoiceGenerateConfig):
        self._config = config
        self._default_client: BaseVoiceGenerationClient | None = None
        self._client_cache: dict[str, BaseVoiceGenerationClient] = {}

    def _get_client(
        self, provider: str | None = None, model_name: str | None = None
    ) -> BaseVoiceGenerationClient:
        if not provider and not model_name:
            if self._default_client is None:
                self._default_client = create_voice_generation_client(self._config)
            return self._default_client

        cache_key = f"{provider or 'default'}:{model_name or 'default'}"
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        client = create_voice_generation_client(
            self._config,
            model_name=model_name,
            provider=provider,
        )
        self._client_cache[cache_key] = client
        return client

    async def generate_voice(
        self,
        text: str,
        **kwargs,
    ) -> VoiceGenerationResult:
        provider = kwargs.pop("provider", None)
        model_name = kwargs.pop("model_name", None)
        normalized_provider = self._normalize_provider(provider)

        try:
            client = self._get_client(provider=normalized_provider, model_name=model_name)
            return await client.generate_voice(
                text=text,
                **kwargs,
            )
        except Exception as exc:
            if not self._should_fallback(normalized_provider):
                logger.exception(
                    "Voice generation failed",
                    extra={
                        "provider": normalized_provider,
                        "model_name": model_name,
                        "kwargs_keys": list(kwargs.keys()),
                    },
                )
                raise

            fallback_provider = VoiceGenerationProvider.GEMINI.value
            if not self._config.has_gemini_tts_credentials():
                logger.exception(
                    "Voice generation failed and Gemini TTS is not configured",
                    extra={
                        "provider": normalized_provider,
                        "model_name": model_name,
                        "kwargs_keys": list(kwargs.keys()),
                    },
                )
                raise

            logger.warning(
                "ElevenLabs failed; falling back to Gemini TTS",
                extra={
                    "provider": normalized_provider,
                    "model_name": model_name,
                    "fallback_provider": fallback_provider,
                    "error": str(exc),
                },
            )
            fallback_kwargs = self._prepare_fallback_kwargs(kwargs)
            fallback_client = self._get_client(
                provider=fallback_provider,
                model_name=fallback_kwargs.pop("model_name", None),
            )
            return await fallback_client.generate_voice(
                text=text,
                **fallback_kwargs,
            )

    def _normalize_provider(self, provider: str | None) -> str | None:
        if provider in PROVIDER_ALIASES:
            return PROVIDER_ALIASES[provider].value
        return provider

    def _should_fallback(self, provider: str | None) -> bool:
        if provider is None:
            return bool(self._config.elevenlabs_api_key)
        return provider == VoiceGenerationProvider.ELEVENLABS.value

    def _prepare_fallback_kwargs(self, kwargs: dict) -> dict:
        fallback_kwargs = dict(kwargs)
        # Remove ElevenLabs-specific fields that don't apply to Gemini TTS.
        fallback_kwargs.pop("pronunciation_dictionary_locators", None)
        fallback_kwargs.pop("previous_text", None)
        fallback_kwargs.pop("next_text", None)
        fallback_kwargs.pop("previous_request_ids", None)
        fallback_kwargs.pop("next_request_ids", None)
        fallback_kwargs.pop("enable_logging", None)
        fallback_kwargs.pop("optimize_streaming_latency", None)
        fallback_kwargs.pop("apply_text_normalization", None)
        fallback_kwargs.pop("apply_language_text_normalization", None)
        # Avoid passing ElevenLabs voice IDs into Gemini.
        fallback_kwargs.pop("voice_id", None)
        return fallback_kwargs
