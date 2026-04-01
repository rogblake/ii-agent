"""FastAPI dependencies for storage."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.core.storage.service import StorageService


def _get_storage_service(container: ContainerDep) -> StorageService:
    return container.storage_service


StorageServiceDep = Annotated[StorageService, Depends(_get_storage_service)]

