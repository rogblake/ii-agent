from ii_agent_tools.integrations.audio_generation.base import (
    AudioGenerationResult,
    BaseAudioGenerationClient,
)
from ii_agent_tools.integrations.audio_generation.config import AudioGenerateConfig
from ii_agent_tools.integrations.audio_generation.factory import (
    create_audio_generation_client,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


class AudioGenerationService:
    """Audio generation service with provider-per-request support."""

    def __init__(self, config: AudioGenerateConfig):
        self._config = config
        self._default_client: BaseAudioGenerationClient | None = None
        self._client_cache: dict[str, BaseAudioGenerationClient] = {}

    def _get_client(
        self, provider: str | None = None, model_name: str | None = None
    ) -> BaseAudioGenerationClient:
        if not provider and not model_name:
            if self._default_client is None:
                self._default_client = create_audio_generation_client(self._config)
            return self._default_client

        cache_key = f"{provider or 'default'}:{model_name or 'default'}"
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        client = create_audio_generation_client(
            self._config,
            model_name=model_name,
            provider=provider,
        )
        self._client_cache[cache_key] = client
        return client

    async def generate_audio(self, prompt: str, **kwargs) -> AudioGenerationResult:
        provider = kwargs.pop("provider", None)
        model_name = kwargs.pop("model_name", None)

        try:
            client = self._get_client(provider=provider, model_name=model_name)
            return await client.generate_audio(prompt=prompt, **kwargs)
        except ValueError:
            raise
        except Exception:
            logger.exception(
                "Audio generation failed",
                extra={
                    "provider": provider,
                    "model_name": model_name,
                    "kwargs_keys": list(kwargs.keys()),
                },
            )
            raise
