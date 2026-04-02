"""FastAPI dependencies for skills domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.config.settings import get_settings
from ii_agent.content.skills.repository import SkillRepository
from ii_agent.content.skills.service import SkillService


# ==================== Repository Dependencies ====================


def get_skill_repository() -> SkillRepository:
    """Provide SkillRepository instance."""
    return SkillRepository()


SkillRepositoryDep = Annotated[SkillRepository, Depends(get_skill_repository)]


# ==================== Service Dependencies ====================


def get_skill_service(
    skill_repo: SkillRepositoryDep,
) -> SkillService:
    """Provide SkillService instance with explicit repo injection."""
    return SkillService(skill_repo=skill_repo, config=get_settings())


SkillServiceDep = Annotated[SkillService, Depends(get_skill_service)]


__all__ = [
    "get_skill_repository",
    "get_skill_service",
    "SkillRepositoryDep",
    "SkillServiceDep",
]
