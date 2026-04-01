"""FastAPI dependencies for files domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.files.repository import FileRepository
from ii_agent.files.service import FileService


# ==================== Repository Dependencies ====================


def get_file_repository() -> FileRepository:
    """Provide FileRepository instance."""
    return FileRepository()


FileRepositoryDep = Annotated[FileRepository, Depends(get_file_repository)]


# ==================== Service Dependencies ====================


def _get_file_service(container: ContainerDep) -> FileService:
    return container.file_service


FileServiceDep = Annotated[FileService, Depends(_get_file_service)]
