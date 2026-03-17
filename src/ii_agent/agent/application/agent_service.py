"""Agent service for managing agent lifecycle."""

from typing import Any, Dict, List, Optional

from ii_agent.core.config.settings import Settings
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.logger import logger
from ii_agent.agent.prompts.plan_mode_prompt import get_plan_mode_prompt
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.core.storage.base import BaseStorage
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.agent.runtime.agents.agent import IIAgent
from ii_agent.agent.runtime.agent_sessions.store import AgentSessionStore
from ii_agent.agent.runtime.factory.factory import AgentFactory
from ii_agent.agent.runtime.skills.db_creator import DbSkillCreator
from ii_agent.agent.runtime.tools.connectors.connector_tool import ConnectorTool
from ii_agent.agent.types import AgentType


class AgentService:
    """Service for managing agent lifecycle and creation."""

    def __init__(self, config: Settings, file_store: BaseStorage):
        self.config = config
        self.file_store = file_store
        self._agent_factory = AgentFactory(config=config)

    async def create_agent_v1(
        self,
        session_info: SessionInfo,
        llm_config: LLMConfig,
        workspace_manager: WorkspaceManager,
        agent_type: AgentType = AgentType.GENERAL,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        default_repository: Optional[Dict[str, str]] = None,
    ) -> IIAgent:
        logger.info(f"[Agent Service] Creating V1 agent for user {session_info.user_id} with storage support for custom skills")
        skill_creator = DbSkillCreator(user_id=session_info.user_id, storage=self.file_store)
        connector_tool = ConnectorTool(
            user_id=session_info.user_id, default_repository=default_repository
        )

        return await self._agent_factory.create_agent(
            user_id=session_info.user_id,
            session_id=str(session_info.id),
            llm_config=llm_config,
            workspace_manager=workspace_manager,
            tool_args=tool_args,
            metadata=metadata,
            agent_type=agent_type,
            session_store=AgentSessionStore(),
            skill_creator=skill_creator,
            connector_tool=connector_tool,
        )

    async def create_plan_agent_v1(
        self,
        session_info: SessionInfo,
        llm_config: LLMConfig,
        workspace_manager: WorkspaceManager,
        system_prompt: Optional[str] = None,
        plan_tools: Optional[List] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IIAgent:
        """Create a V1 plan mode agent with MilestoneTool and standard toolset.

        Args:
            session_info: Session information
            llm_config: LLM configuration
            workspace_manager: Workspace manager instance
            system_prompt: Optional custom prompt (defaults to plan mode prompt)
            plan_tools: List of plan-specific tools (MilestoneToolV1, etc.)
            tool_args: Tool configuration arguments
            metadata: Additional metadata

        Returns:
            Configured IIAgent instance for plan mode
        """
        logger.info(
            f"[Agent Service] Creating V1 plan agent for user {session_info.user_id}"
        )

        # Use plan mode prompt if not provided
        if system_prompt is None:
            system_prompt = get_plan_mode_prompt()

        skill_creator = DbSkillCreator(
            user_id=session_info.user_id, storage=self.file_store
        )
        connector_tool = ConnectorTool(user_id=session_info.user_id)

        # Create agent with plan-specific system prompt
        agent = await self._agent_factory.create_agent(
            user_id=session_info.user_id,
            session_id=str(session_info.id),
            llm_config=llm_config,
            workspace_manager=workspace_manager,
            tool_args=tool_args,
            metadata=metadata,
            agent_type=AgentType.GENERAL,
            session_store=AgentSessionStore(),
            skill_creator=skill_creator,
            connector_tool=connector_tool,
            system_prompt=system_prompt,
        )

        # Add plan-specific tools
        if plan_tools:
            for tool in plan_tools:
                agent.add_tool(tool)
            logger.info(f"Added {len(plan_tools)} plan-specific tools to agent")

        return agent

    async def create_plan_suggestions_agent_v1(
        self,
        session_info: SessionInfo,
        llm_config: LLMConfig,
        workspace_manager: WorkspaceManager,
        system_prompt: str,
        plan_tools: Optional[List] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IIAgent:
        """Create a V1 plan suggestions agent with PlanModificationSuggestionsTool.

        Args:
            session_info: Session information
            llm_config: LLM configuration
            workspace_manager: Workspace manager instance
            system_prompt: Custom prompt for generating suggestions (required)
            plan_tools: List of plan-specific tools (PlanModificationSuggestionsToolV1, etc.)
            tool_args: Tool configuration arguments
            metadata: Additional metadata

        Returns:
            Configured IIAgent instance for plan suggestions
        """
        logger.info(
            f"[Agent Service] Creating V1 plan suggestions agent for user {session_info.user_id}"
        )

        skill_creator = DbSkillCreator(
            user_id=session_info.user_id, storage=self.file_store
        )
        connector_tool = ConnectorTool(user_id=session_info.user_id)

        # Create agent with suggestions-specific system prompt
        agent = await self._agent_factory.create_agent(
            user_id=session_info.user_id,
            session_id=str(session_info.id),
            llm_config=llm_config,
            workspace_manager=workspace_manager,
            tool_args=tool_args,
            metadata=metadata,
            agent_type=AgentType.GENERAL,
            session_store=AgentSessionStore(),
            skill_creator=skill_creator,
            connector_tool=connector_tool,
            system_prompt=system_prompt,
        )

        # Add plan-specific tools
        if plan_tools:
            for tool in plan_tools:
                agent.add_tool(tool)
            logger.info(f"Added {len(plan_tools)} plan suggestion tools to agent")

        return agent
