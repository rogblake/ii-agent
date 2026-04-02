"""Registry for media type handlers."""

from typing import Callable, Type

# Forward declaration to avoid circular import
# BaseMediaHandler will be imported in handlers/base.py
BaseMediaHandler = object


# Registry mapping media type names to handler classes
_HANDLER_REGISTRY: dict[str, Type[BaseMediaHandler]] = {}


def register_handler(media_type: str) -> Callable[[Type[BaseMediaHandler]], Type[BaseMediaHandler]]:
    """
    Decorator to register a media handler.

    Usage:
        @register_handler("image")
        class ImageMediaHandler(BaseMediaHandler):
            ...

    Args:
        media_type: Type of media (e.g., "image", "video", "poster")

    Returns:
        Decorator function
    """
    def decorator(cls: Type[BaseMediaHandler]) -> Type[BaseMediaHandler]:
        _HANDLER_REGISTRY[media_type] = cls
        return cls
    return decorator


def get_handler(media_type: str) -> Type[BaseMediaHandler] | None:
    """
    Get a registered handler by media type.

    Args:
        media_type: Type of media (e.g., "image")

    Returns:
        Handler class or None if not found
    """
    return _HANDLER_REGISTRY.get(media_type)


def list_handlers() -> list[str]:
    """
    List all registered media type names.

    Returns:
        List of media type names
    """
    return list(_HANDLER_REGISTRY.keys())


def is_handler_registered(media_type: str) -> bool:
    """
    Check if a handler is registered for a media type.

    Args:
        media_type: Type of media

    Returns:
        True if registered, False otherwise
    """
    return media_type in _HANDLER_REGISTRY
