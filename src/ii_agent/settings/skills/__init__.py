"""Skill management domain module."""

from .dependencies import SkillRepositoryDep, SkillServiceDep
from .exceptions import BuiltinSkillDeleteError, SkillAlreadyExistsError, SkillNotFoundError
from .models import Skill, SkillSource
from .repository import SkillRepository
from .router import router
from .service import SkillService

__all__ = [
    # Models
    "Skill",
    "SkillSource",
    # Repository
    "SkillRepository",
    # Service
    "SkillService",
    # Dependencies
    "SkillRepositoryDep",
    "SkillServiceDep",
    # Exceptions
    "SkillNotFoundError",
    "SkillAlreadyExistsError",
    "BuiltinSkillDeleteError",
    # Router
    "router",
]
