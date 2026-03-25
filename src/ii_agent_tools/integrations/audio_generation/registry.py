from typing import Callable, Type

from .base import BaseAudioGenerationClient


_PROVIDER_REGISTRY: dict[str, Type[BaseAudioGenerationClient]] = {}


def register_provider(
    name: str,
) -> Callable[[Type[BaseAudioGenerationClient]], Type[BaseAudioGenerationClient]]:
    """Decorator to register an audio generation provider."""

    def decorator(
        cls: Type[BaseAudioGenerationClient],
    ) -> Type[BaseAudioGenerationClient]:
        _PROVIDER_REGISTRY[name] = cls
        return cls

    return decorator


def get_provider(name: str) -> Type[BaseAudioGenerationClient] | None:
    return _PROVIDER_REGISTRY.get(name)


def list_providers() -> list[str]:
    return list(_PROVIDER_REGISTRY.keys())
