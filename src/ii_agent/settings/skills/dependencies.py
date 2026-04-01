"""FastAPI dependencies for skills domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.settings.skills.repository import SkillRepository
from ii_agent.settings.skills.service import SkillService


# ==================== Repository Dependencies ====================


def get_skill_repository() -> SkillRepository:
    """Provide SkillRepository instance."""
    return SkillRepository()


SkillRepositoryDep = Annotated[SkillRepository, Depends(get_skill_repository)]


# ==================== Service Dependencies ====================


def _get_skill_service(container: ContainerDep) -> SkillService:
    return container.skill_service


SkillServiceDep = Annotated[SkillService, Depends(_get_skill_service)]
