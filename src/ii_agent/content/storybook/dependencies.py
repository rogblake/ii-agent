"""FastAPI dependencies for storybook domain.

All services are container-backed thin accessors.
Repositories remain as factory functions (stateless leaf nodes).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.content.storybook.ai_edit_service import StorybookAIEditService
from ii_agent.content.storybook.edit_service import StorybookEditService
from ii_agent.content.storybook.export_service import StorybookExportService
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.storybook.service import StorybookService
from ii_agent.content.storybook.version_service import StorybookVersionService
from ii_agent.content.storybook.voice_service import StorybookVoiceService


# ==================== Repository Dependencies ====================


def get_storybook_repository() -> StorybookRepository:
    """Provide StorybookRepository instance."""
    return StorybookRepository()


StorybookRepositoryDep = Annotated[StorybookRepository, Depends(get_storybook_repository)]


# ==================== Service Dependencies (container-backed) =============


def _get_storybook_service(container: ContainerDep) -> StorybookService:
    return container.storybook_service


StorybookServiceDep = Annotated[StorybookService, Depends(_get_storybook_service)]


def _get_storybook_edit_service(container: ContainerDep) -> StorybookEditService:
    return container.storybook_edit_service


StorybookEditServiceDep = Annotated[StorybookEditService, Depends(_get_storybook_edit_service)]


def _get_storybook_export_service(container: ContainerDep) -> StorybookExportService:
    return container.storybook_export_service


StorybookExportServiceDep = Annotated[
    StorybookExportService, Depends(_get_storybook_export_service)
]


def _get_storybook_version_service(container: ContainerDep) -> StorybookVersionService:
    return container.storybook_version_service


StorybookVersionServiceDep = Annotated[
    StorybookVersionService, Depends(_get_storybook_version_service)
]


def _get_storybook_voice_service(container: ContainerDep) -> StorybookVoiceService:
    return container.storybook_voice_service


StorybookVoiceServiceDep = Annotated[StorybookVoiceService, Depends(_get_storybook_voice_service)]


def _get_storybook_ai_edit_service(container: ContainerDep) -> StorybookAIEditService:
    return container.storybook_ai_edit_service


StorybookAIEditServiceDep = Annotated[
    StorybookAIEditService, Depends(_get_storybook_ai_edit_service)
]


__all__ = [
    "get_storybook_repository",
    "StorybookRepositoryDep",
    "StorybookServiceDep",
    "StorybookEditServiceDep",
    "StorybookExportServiceDep",
    "StorybookVersionServiceDep",
    "StorybookVoiceServiceDep",
    "StorybookAIEditServiceDep",
]
