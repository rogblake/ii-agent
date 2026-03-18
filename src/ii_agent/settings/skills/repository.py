"""Repository layer for skills domain - data access only."""

from typing import List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.repository import BaseRepository
from ii_agent.settings.skills.models import Skill, SkillSource


class SkillRepository(BaseRepository[Skill]):
    """Data access layer for Skill model."""

    model = Skill

    async def get_by_id_for_user(
        self, db: AsyncSession, skill_id: str, user_id: str
    ) -> Optional[Skill]:
        """Get a skill that is either builtin or owned by user."""
        result = await db.execute(
            select(Skill).where(
                and_(
                    Skill.id == skill_id,
                    or_(
                        Skill.user_id.is_(None),
                        Skill.user_id == user_id,
                    ),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_user_skill(
        self, db: AsyncSession, skill_id: str, user_id: str
    ) -> Optional[Skill]:
        """Get a skill owned by user (not builtin)."""
        result = await db.execute(
            select(Skill).where(
                and_(
                    Skill.id == skill_id,
                    Skill.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_builtin_by_id(self, db: AsyncSession, skill_id: str) -> Optional[Skill]:
        """Get a builtin skill by ID."""
        result = await db.execute(
            select(Skill).where(
                and_(
                    Skill.id == skill_id,
                    Skill.user_id.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name_and_user(
        self, db: AsyncSession, name: str, user_id: str
    ) -> Optional[Skill]:
        """Get a skill by name for a specific user."""
        result = await db.execute(
            select(Skill).where(
                and_(
                    Skill.user_id == user_id,
                    Skill.name == name,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_user_builtin_override(
        self, db: AsyncSession, user_id: str, skill_name: str
    ) -> Optional[Skill]:
        """Get user's override for a builtin skill."""
        result = await db.execute(
            select(Skill).where(
                and_(
                    Skill.user_id == user_id,
                    Skill.name == skill_name,
                    Skill.source == SkillSource.BUILTIN.value,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, db: AsyncSession, user_id: str) -> List[Skill]:
        """List all skills owned by a user."""
        result = await db.execute(select(Skill).where(Skill.user_id == user_id))
        return list(result.scalars().all())

    async def list_builtin(self, db: AsyncSession) -> List[Skill]:
        """List all builtin skills (user_id IS NULL)."""
        result = await db.execute(select(Skill).where(Skill.user_id.is_(None)))
        return list(result.scalars().all())

    async def delete(self, db: AsyncSession, skill: Skill) -> None:
        """Delete a skill."""
        await db.delete(skill)
        await db.flush()
