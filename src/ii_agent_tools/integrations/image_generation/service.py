from typing import Literal
from ii_agent_tools.integrations.image_generation.base import (
    BaseImageGenerationClient,
    ImageGenerationResult,
)
from ii_agent_tools.integrations.image_generation.config import ImageGenerateConfig
from ii_agent_tools.integrations.image_generation.factory import (
    create_image_generation_client,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


class ImageGenerationService:
    """Image generation service with provider-per-request support."""

    def __init__(self, config: ImageGenerateConfig):
        self._config = config
        self._default_client: BaseImageGenerationClient | None = None
        self._client_cache: dict[str, BaseImageGenerationClient] = {}

    def _get_client(
        self, provider: str | None = None, model_name: str | None = None
    ) -> BaseImageGenerationClient:
        # If no provider specified, use default client
        if not provider and not model_name:
            if self._default_client is None:
                self._default_client = create_image_generation_client(self._config)
            return self._default_client

        # Create cache key for provider + model combination
        cache_key = f"{provider or 'default'}:{model_name or 'default'}"

        # Return cached client if available
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        # Create new client and cache it
        client = create_image_generation_client(
            self._config,
            model_name=model_name,
            provider=provider,
        )
        self._client_cache[cache_key] = client
        return client

    async def generate_image(
        self,
        prompt: str,
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
        ] = "1:1",
        **kwargs,
    ) -> ImageGenerationResult:
        provider = kwargs.pop("provider", None)
        model_name = kwargs.pop("model_name", None)

        try:
            client = self._get_client(provider=provider, model_name=model_name)
            return await client.generate_image(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                **kwargs,
            )
        except ValueError:
            raise
        except Exception:
            logger.exception(
                "Image generation failed",
                extra={
                    "provider": provider,
                    "model_name": model_name,
                    "aspect_ratio": aspect_ratio,
                    "image_urls": kwargs.get("image_urls"),
                    "kwargs_keys": list(kwargs.keys()),
                },
            )
            raise
