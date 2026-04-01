"""Shared Celery helpers for worker processes."""

from ii_agent.core.container import ApplicationContainer

_celery_container: ApplicationContainer | None = None


def get_celery_container() -> ApplicationContainer:
    """Return a cached ServiceContainer for Celery workers."""
    global _celery_container
    if _celery_container is None:
        _celery_container = ApplicationContainer.init()
    return _celery_container
