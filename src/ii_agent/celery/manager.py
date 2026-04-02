"""Shared Celery helpers for worker processes."""

from ii_agent.core.container import ServiceContainer

_celery_container: ServiceContainer | None = None


def get_celery_container() -> ServiceContainer:
    """Return a cached ServiceContainer for Celery workers."""
    global _celery_container
    if _celery_container is None:
        _celery_container = ServiceContainer.create()
    return _celery_container
