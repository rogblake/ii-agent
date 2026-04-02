"""Factory for creating LLM providers (updated for official SDKs)."""

import logging
from typing import Type

from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.chat.llm.custom import CustomProvider
from ii_agent.chat.base import LLMClient
from ii_agent.chat.llm.anthropic import AnthropicProvider
from ii_agent.chat.llm.openai import OpenAIProvider
from ii_agent.chat.llm.gemini import GeminiProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory for creating provider-specific LLM clients using official SDKs."""

    # Registry mapping providers to provider classes
    _provider_registry: dict[Provider, Type[LLMClient]] = {
        Provider.ANTHROPIC: AnthropicProvider,
        Provider.OPENAI: OpenAIProvider,
        Provider.GOOGLE: GeminiProvider,
        Provider.CUSTOM: CustomProvider,
    }

    @classmethod
    def create_provider(cls, llm_config: ModelConfig) -> LLMClient:
        """
        Create appropriate provider based on provider type.

        Args:
            llm_config: LLM configuration with provider

        Returns:
            Provider instance using official SDK

        Raises:
            ValueError: If provider not supported
        """
        provider = llm_config.provider

        provider_class = cls._provider_registry.get(provider)

        if not provider_class:
            supported_types = ", ".join(t.value for t in cls._provider_registry.keys())
            raise ValueError(
                f"Unsupported provider: {provider.value}. "
                f"Supported providers: {supported_types}"
            )

        logger.info(
            f"Creating {provider_class.__name__} for model: {llm_config.model} "
            f"(provider: {provider.value})"
        )

        cls = provider_class

        if (
            provider == Provider.OPENAI and llm_config.base_url is not None
        ):  # NOTE: fix backwards compatibility
            cls = CustomProvider
        return cls(llm_config)

    @classmethod
    def register_provider(
        cls,
        provider: Provider,
        provider_class: Type[LLMClient],
    ) -> None:
        """
        Register a new provider implementation.

        This allows extending the factory with custom providers at runtime.

        Args:
            provider: Provider enum value
            provider_class: Provider class to register

        Example:
            ```python
            class CustomProvider(ProviderClient):
                ...

            LLMProviderFactory.register_provider(
                Provider.CUSTOM,
                CustomProvider
            )
            ```
        """
        logger.info(
            f"Registering provider {provider_class.__name__} for {provider.value}"
        )
        cls._provider_registry[provider] = provider_class

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """
        Get list of supported provider types.

        Returns:
            List of supported provider values
        """
        return [provider.value for provider in cls._provider_registry.keys()]


def get_client(config: ModelConfig) -> LLMClient:
    """Get an LLM client for a given config. Convenience wrapper around LLMProviderFactory."""
    return LLMProviderFactory.create_provider(config)
