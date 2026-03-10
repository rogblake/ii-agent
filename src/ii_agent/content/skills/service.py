"""Service layer for skills domain - business logic only."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.content.skills.exceptions import (
    BuiltinSkillDeleteError,
    SkillAlreadyExistsError,
)
from ii_agent.content.skills.models import Skill, SkillSource
from ii_agent.content.skills.repository import SkillRepository
from ii_agent.content.skills.schemas import SkillInfo, SkillList
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.storage import BaseStorage
from ii_agent.engine.runtime.skills.github import (
    GitHubDownloadService,
    GitHubSkillError,
)
from ii_agent.engine.runtime.skills.skills_ref.errors import ParseError, ValidationError
from ii_agent.engine.runtime.skills.storage import upload_skill_to_gcs

logger = logging.getLogger(__name__)

SANDBOX_SKILLS_PATH = "/workspace/.skills"


class SkillService:
    """Service for managing skills - business logic layer."""

    def __init__(self, *, skill_repo: SkillRepository, config: Settings) -> None:
        self._config = config
        self._repo = skill_repo

    async def add_skill_from_github(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        github_url: str,
        storage: BaseStorage,
        github_token: Optional[str] = None,
    ) -> SkillInfo:
        """Download skill from GitHub and store in GCS.

        Raises:
            SkillAlreadyExistsError: If skill with same name exists.
            GitHubSkillError: If GitHub URL parsing or download fails.
            ParseError: If skill parsing fails.
            ValidationError: If skill validation fails.
        """
        logger.info(f"Adding skill from GitHub: {github_url}")

        async with GitHubDownloadService(github_token=github_token) as github_service:
            try:
                github_path = github_service.parse_url(github_url)
            except GitHubSkillError as e:
                logger.error(f"Failed to parse GitHub URL: {e}")
                raise

            try:
                properties, files = await github_service.download_folder(github_path)
            except (GitHubSkillError, ParseError, ValidationError) as e:
                logger.error(f"Failed to download skill: {e}")
                raise

        skill_name = properties.name

        existing = await self._repo.get_by_name_and_user(db, skill_name, user_id)
        if existing:
            raise SkillAlreadyExistsError(
                f"Skill '{skill_name}' already exists. "
                f"Delete it first or choose a skill with a different name."
            )

        storage_path = await upload_skill_to_gcs(
            storage=storage,
            user_id=user_id,
            skill_name=skill_name,
            files=files,
        )

        skill_md_file = next(
            (f for f in files if f.path.lower() == "skill.md"),
            None,
        )
        skill_md_content = skill_md_file.content.decode("utf-8") if skill_md_file else ""

        allowed_tools = []
        if properties.allowed_tools:
            allowed_tools = properties.allowed_tools.split()

        skill = Skill(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=skill_name,
            description=properties.description,
            source=SkillSource.GITHUB.value,
            source_url=github_url,
            skill_md_content=skill_md_content,
            sandbox_path=f"{SANDBOX_SKILLS_PATH}/{skill_name}",
            storage_uri=storage_path,
            license=properties.license,
            compatibility=properties.compatibility,
            allowed_tools=allowed_tools,
            is_enabled=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        created = await self._repo.create(db, skill)
        logger.info(f"Created skill '{skill_name}' for user {user_id}")
        return _to_skill_info(created)

    async def list_skills(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        include_builtin: bool = True,
    ) -> SkillList:
        """List skills for a user."""
        user_skills = await self._repo.list_by_user(db, user_id)

        builtin_overrides = {
            s.name: s for s in user_skills
            if s.source == SkillSource.BUILTIN.value
        }

        custom_skills = [s for s in user_skills if s.source != SkillSource.BUILTIN.value]

        skills_to_return: list[SkillInfo] = []
        builtin_count = 0
        custom_count = len(custom_skills)

        if include_builtin:
            builtin_skills = await self._repo.list_builtin(db)

            for builtin_skill in builtin_skills:
                if builtin_skill.name in builtin_overrides:
                    override = builtin_overrides[builtin_skill.name]
                    skills_to_return.append(
                        _to_skill_info_with_override(builtin_skill, override.is_enabled)
                    )
                else:
                    skills_to_return.append(_to_skill_info(builtin_skill))
                builtin_count += 1

        skills_to_return.extend([_to_skill_info(s) for s in custom_skills])

        skills_to_return.sort(
            key=lambda s: (0 if s.source == SkillSource.BUILTIN.value else 1, s.name.lower())
        )

        return SkillList(
            skills=skills_to_return,
            builtin_count=builtin_count,
            custom_count=custom_count,
        )

    async def get_skill(
        self,
        db: AsyncSession,
        *,
        skill_id: str,
        user_id: str,
    ) -> Optional[SkillInfo]:
        """Get skill by ID (builtin or user's own)."""
        skill = await self._repo.get_by_id_for_user(db, skill_id, user_id)
        return _to_skill_info(skill) if skill else None

    async def toggle_skill(
        self,
        db: AsyncSession,
        *,
        skill_id: str,
        user_id: str,
        is_enabled: bool,
    ) -> Optional[SkillInfo]:
        """Toggle skill enabled state."""
        skill = await self._repo.get_by_id(db, skill_id)
        if not skill:
            return None

        # Handle built-in skills (user_id is None)
        if skill.user_id is None:
            override = await self._repo.get_user_builtin_override(db, user_id, skill.name)

            if is_enabled:
                if override:
                    await self._repo.delete(db, override)
                    logger.info(f"Deleted override for builtin skill '{skill.name}' (re-enabled)")
                return _to_skill_info(skill)
            else:
                if override:
                    override.is_enabled = False
                    override.updated_at = datetime.now(timezone.utc)
                    await self._repo.update(db, override)
                    logger.info(f"Updated override for builtin skill '{skill.name}' -> disabled")
                else:
                    override = Skill(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        name=skill.name,
                        description=skill.description,
                        source=SkillSource.BUILTIN.value,
                        source_url=skill.source_url,
                        skill_md_content="",
                        sandbox_path=skill.sandbox_path,
                        storage_uri=skill.storage_uri,
                        license=skill.license,
                        compatibility=skill.compatibility,
                        allowed_tools=[],
                        is_enabled=False,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    await self._repo.create(db, override)
                    logger.info(f"Created override for builtin skill '{skill.name}' -> disabled")

                return _to_skill_info_with_override(skill, is_enabled=False)

        # Handle user's custom skills
        if skill.user_id != user_id:
            return None

        skill.is_enabled = is_enabled
        skill.updated_at = datetime.now(timezone.utc)
        await self._repo.update(db, skill)
        logger.info(f"Toggled skill '{skill.name}' -> {is_enabled}")
        return _to_skill_info(skill)

    async def delete_skill(
        self,
        db: AsyncSession,
        *,
        skill_id: str,
        user_id: str,
        storage: Optional[BaseStorage] = None,
    ) -> bool:
        """Delete a custom skill.

        Raises:
            BuiltinSkillDeleteError: If trying to delete a builtin skill.
        """
        skill = await self._repo.get_user_skill(db, skill_id, user_id)

        if not skill:
            builtin = await self._repo.get_builtin_by_id(db, skill_id)
            if builtin:
                raise BuiltinSkillDeleteError("Cannot delete built-in skills.")
            return False

        skill_name = skill.name
        await self._repo.delete(db, skill)
        logger.info(f"Deleted skill '{skill_name}' for user {user_id}")
        return True


# ---------------------------------------------------------------------------
# Private converter helpers
# ---------------------------------------------------------------------------


def _to_skill_info(skill: Skill) -> SkillInfo:
    """Convert database Skill model to response model."""
    return SkillInfo(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        source=skill.source,
        source_url=skill.source_url,
        is_enabled=skill.is_enabled,
        license=skill.license,
        compatibility=skill.compatibility,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


def _to_skill_info_with_override(skill: Skill, is_enabled: bool) -> SkillInfo:
    """Convert database Skill model to response model with overridden is_enabled."""
    return SkillInfo(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        source=skill.source,
        source_url=skill.source_url,
        is_enabled=is_enabled,
        license=skill.license,
        compatibility=skill.compatibility,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )
