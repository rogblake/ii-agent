"""Storage module — single-bucket async object storage.

Usage::

    # Via DI in FastAPI routes:
    from ii_agent.core.storage.dependencies import StorageServiceDep

    # Raw provider access (singleton, safe outside DI):
    from ii_agent.core.storage import get_storage
    provider = get_storage()
    await provider.write("custom/path", data)
"""

from ii_agent.core.storage.client import get_storage, set_storage, reset_storage
from ii_agent.core.storage.dependencies import StorageServiceDep
from ii_agent.core.storage.exceptions import (
    StorageError,
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from ii_agent.core.storage.path_resolver import PathResolver, path_resolver
from ii_agent.core.storage.providers.base import StorageProvider
from ii_agent.core.storage.service import StorageService

__all__ = [
    # Service
    "StorageService",
    "StorageServiceDep",
    # Raw provider
    "StorageProvider",
    "get_storage",
    "set_storage",
    "reset_storage",
    # Path resolver
    "PathResolver",
    "path_resolver",
    # Errors
    "StorageError",
    "StorageObjectNotFoundError",
    "StoragePermissionError",
]
