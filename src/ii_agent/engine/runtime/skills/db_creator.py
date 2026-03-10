"""Database-backed skill creator implementation."""

from typing import TYPE_CHECKING, Optional

from ii_agent.core.db.manager import get_db_session_local
from ii_agent.engine.runtime.skills.base import SkillCreator
from ii_agent.engine.runtime.skills.loader import get_user_skills
from ii_agent.engine.runtime.skills.prompt_db import generate_skill_tool_description
from ii_agent.engine.runtime.tools.skill import SkillTool
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.core.storage import BaseStorage

class DbSkillCreator(SkillCreator):
    """Database-backed skill creator.

    Creates SkillTool instances by loading skills from the database
    for a specific user. Supports both builtin and user-defined skills.

    Args:
        user_id: User ID to load skills for
        enabled_only: Only include enabled skills (default: True)
        storage: GCS storage client for custom skills stored in cloud storage.
            Required when user has custom skills from GitHub.

    Example:
        creator = DbSkillCreator(user_id=current_user.id, storage=storage_client)
        skill_tool = await creator.create_skill_tool()
    """

    def __init__(
        self,
        user_id: str,
        enabled_only: bool = True,
        storage: Optional["BaseStorage"] = None,
    ):
        self._user_id = user_id
        self._enabled_only = enabled_only
        self._storage = storage

    async def create_skill_tool(self) -> Optional[SkillTool]:
        """Create a SkillTool from database skills.

        Returns:
            SkillTool configured with user's skills, or None if:
            - No skills available for user
            - Database query fails
        """
        try:
            async with get_db_session_local() as db:
                # Get user's skills (builtin + user, with override logic)
                skills = await get_user_skills(
                    db,
                    self._user_id,
                    enabled_only=self._enabled_only,
                )

                if not skills:
                    logger.info(f"No skills available for user {self._user_id}")
                    return None

                # Generate tool description with available skills XML
                description = generate_skill_tool_description(skills)

                # Build skills registry mapping name -> Skill DB model
                # This provides access to storage_uri for each skill
                skills_registry = {skill.name: skill for skill in skills}

                logger.info(
                    f"Created SkillTool for user {self._user_id} with {len(skills_registry)} skills"
                )

                return SkillTool(
                    description=description,
                    skills_registry=skills_registry,
                    storage=self._storage,
                )
        except Exception as e:
            logger.error(f"Failed to create SkillTool for user {self._user_id}: {e}")
            return None
