"""FastAPI dependency factories for sandboxes domain."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.service import SandboxService
from ii_agent.core.dependencies import ContainerDep


def get_sandbox_repository() -> SandboxRepository:
    return SandboxRepository()


SandboxRepositoryDep = Annotated[SandboxRepository, Depends(get_sandbox_repository)]


def _get_sandbox_service(container: ContainerDep) -> SandboxService:
    return container.sandbox_service


SandboxServiceDep = Annotated[SandboxService, Depends(_get_sandbox_service)]
