from typing import Callable, Type
from .base import BaseImageGenerationClient


# Registry mapping provider names to client classes
_PROVIDER_REGISTRY: dict[str, Type[BaseImageGenerationClient]] = {}


def register_provider(
    name: str,
) -> Callable[[Type[BaseImageGenerationClient]], Type[BaseImageGenerationClient]]:
    """
    Decorator to register an image generation provider.

    Usage:
        @register_provider("openai")
        class OpenAIImageGenerationClient(BaseImageGenerationClient):
            ...
    """

    def decorator(
        cls: Type[BaseImageGenerationClient],
    ) -> Type[BaseImageGenerationClient]:
        _PROVIDER_REGISTRY[name] = cls
        return cls

    return decorator


def get_provider(name: str) -> Type[BaseImageGenerationClient] | None:
    """Get a registered provider by name."""
    return _PROVIDER_REGISTRY.get(name)


def list_providers() -> list[str]:
    """List all registered provider names."""
    return list(_PROVIDER_REGISTRY.keys())


def is_provider_registered(name: str) -> bool:
    """Check if a provider is registered."""
    return name in _PROVIDER_REGISTRY
