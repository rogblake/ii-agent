from typing import Callable, Type
from .base import BaseVoiceGenerationClient


_PROVIDER_REGISTRY: dict[str, Type[BaseVoiceGenerationClient]] = {}


def register_provider(
    name: str,
) -> Callable[[Type[BaseVoiceGenerationClient]], Type[BaseVoiceGenerationClient]]:
    """
    Decorator to register a voice generation provider.
    """

    def decorator(
        cls: Type[BaseVoiceGenerationClient],
    ) -> Type[BaseVoiceGenerationClient]:
        _PROVIDER_REGISTRY[name] = cls
        return cls

    return decorator


def get_provider(name: str) -> Type[BaseVoiceGenerationClient] | None:
    """Get a registered provider by name."""
    return _PROVIDER_REGISTRY.get(name)


def list_providers() -> list[str]:
    """List all registered provider names."""
    return list(_PROVIDER_REGISTRY.keys())


def is_provider_registered(name: str) -> bool:
    """Check if a provider is registered."""
    return name in _PROVIDER_REGISTRY
