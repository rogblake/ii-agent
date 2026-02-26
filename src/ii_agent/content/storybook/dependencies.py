"""FastAPI dependencies for storybook domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.billing.credits.dependencies import CreditServiceDep
from ii_agent.content.storybook.repository import StorybookRepository
from ii_agent.content.storybook.service import StorybookService
from ii_agent.content.storybook.export_service import StorybookExportService
from ii_agent.content.storybook.version_service import StorybookVersionService
from ii_agent.content.storybook.voice_service import StorybookVoiceService
from ii_agent.content.storybook.edit_service import StorybookEditService


# ==================== Repository Dependencies ====================


def get_storybook_repository() -> StorybookRepository:
    """Provide StorybookRepository instance."""
    return StorybookRepository()


StorybookRepositoryDep = Annotated[StorybookRepository, Depends(get_storybook_repository)]


# ==================== Service Dependencies ====================


def get_storybook_service(
    repo: StorybookRepositoryDep,
) -> StorybookService:
    """Provide StorybookService instance with explicit repo injection."""
    return StorybookService(repo=repo, config=get_settings())


StorybookServiceDep = Annotated[StorybookService, Depends(get_storybook_service)]


def get_storybook_export_service(
    storybook_service: StorybookServiceDep,
) -> StorybookExportService:
    """Provide StorybookExportService instance."""
    return StorybookExportService(storybook_service=storybook_service)


def get_storybook_version_service(
    repo: StorybookRepositoryDep,
    storybook_service: StorybookServiceDep,
) -> StorybookVersionService:
    """Provide StorybookVersionService instance."""
    return StorybookVersionService(
        repo=repo, storybook_service=storybook_service, config=get_settings()
    )


def get_storybook_voice_service(
    repo: StorybookRepositoryDep,
    storybook_service: StorybookServiceDep,
    credit_service: CreditServiceDep,
) -> StorybookVoiceService:
    """Provide StorybookVoiceService instance."""
    return StorybookVoiceService(
        repo=repo,
        storybook_service=storybook_service,
        config=get_settings(),
        credit_service=credit_service,
    )


def get_storybook_edit_service(
    repo: StorybookRepositoryDep,
    version_service: StorybookVersionServiceDep,
) -> StorybookEditService:
    """Provide StorybookEditService instance."""
    return StorybookEditService(
        repo=repo,
        version_service=version_service,
    )


StorybookExportServiceDep = Annotated[StorybookExportService, Depends(get_storybook_export_service)]
StorybookVersionServiceDep = Annotated[StorybookVersionService, Depends(get_storybook_version_service)]
StorybookVoiceServiceDep = Annotated[StorybookVoiceService, Depends(get_storybook_voice_service)]
StorybookEditServiceDep = Annotated[StorybookEditService, Depends(get_storybook_edit_service)]
