"""Abstract base class for skill creation strategies."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ii_agent.agents.tools.skill import SkillTool


class SkillCreator(ABC):
    """Abstract interface for creating SkillTool instances.

    This abstraction allows different implementations for skill creation:
    - DbSkillCreator: Database-backed skills (production)
    - FileSkillCreator: File-based skills (local development)
    - MockSkillCreator: Testing/CI environments

    Example usage:
        skill_creator = DbSkillCreator(user_id="user123")
        skill_tool = await skill_creator.create_skill_tool()
        if skill_tool:
            agent_tools.append(skill_tool)
    """

    @abstractmethod
    async def create_skill_tool(self) -> Optional["SkillTool"]:
        """Create a SkillTool instance with user's available skills.

        Returns:
            SkillTool configured with user's skills, or None if no skills available
            or skill creation is disabled.
        """
        pass
