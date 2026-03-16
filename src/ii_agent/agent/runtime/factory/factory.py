"""Agent factory for creating configured agent instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.agent.prompts.agent_prompts import get_system_prompt_for_agent_type
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.agent.runtime.agents.agent import IIAgent
from ii_agent.agent.types import AgentType, Provider
from ii_agent.agent.runtime.skills.base import SkillCreator
from ii_agent.agent.runtime.tools.connectors import BaseConnectorTool
from ii_agent.agent.runtime.factory.tools import AgentConfigManager
from ii_agent.agent.runtime.factory.tool_manager import AgentToolManager
from ii_agent.agent.runtime.models.utils import get_model
from ii_agent.agent.runtime.agent_sessions import SessionStore
from ii_agent.agent.runtime.tools.task import SYSTEM_PROMPT, TaskAgentTool, DESCRIPTION
from ii_agent.agent.runtime.tools.dependencies import ToolDependencies
from ii_agent.core.logger import logger

PROVIDER_SPEC_MAP: Dict[APITypes, Provider] = {
    APITypes.OPENAI: Provider.OPENAI,
    APITypes.ANTHROPIC: Provider.ANTHROPIC,
    APITypes.GEMINI: Provider.GOOGLE,
    APITypes.CUSTOM: Provider.CUSTOM,
}

if TYPE_CHECKING:
    from ii_agent.core.config.settings import Settings


class AgentFactory:
    """Factory for creating configured agent instances."""

    def __init__(self, config: "Settings"):
        """Initialize the agent factory.

        Args:
            config: II Agent configuration
        """
        self.config = config

    async def create_agent(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        agent_type: AgentType = AgentType.GENERAL,
        workspace_manager: Optional[WorkspaceManager] = None,
        session_store: Optional[SessionStore] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        skill_creator: Optional[SkillCreator] = None,
        connector_tool: Optional[BaseConnectorTool] = None,
    ) -> IIAgent:
        """Create a configured agent instance.

        The factory filters the provided tools based on agent type configuration
        and tool_args. The caller is responsible for loading the tools.
        tools_enabled = {
            "deep_research": false,
            "design_document": false,
            "pdf": true,
            "media_generation": false,
            "audio_generation": false,
            "browser": true,
            "enable_reviewer": false,
            "codex_tools": false,
            "claude_code": false
        }

        Args:
            user_id: User ID
            session_id: Session ID
            llm_config: LLM configuration
            agent_type: Type of agent to create
            workspace_manager: Workspace manager instance
            session_store: Session store for persistence
            tool_args: Tool configuration arguments (media_generation, browser, etc.)
            metadata: Additional metadata
            system_prompt: Optional custom system prompt
            skill_creator: Optional skill creator for loading user-specific skills
            connector_tool: Optional connector tool for loading user-specific connectors

        Returns:
            Configured IIAgent instance
        """
        logger.info(f"Creating {agent_type} agent for session {session_id}")

        # Parse tool_args
        tool_args = tool_args or {}
        has_media = tool_args.get("media_generation", False)
        has_browser = tool_args.get("browser", False)
        has_task_agent = tool_args.get("task_agent", False)
        has_researcher = tool_args.get("deep_research", False)
        has_design_doc = tool_args.get("design_document", False)

        # Get LLM client and model
        provider = PROVIDER_SPEC_MAP.get(llm_config.api_type, Provider.CUSTOM)
        # Resolve model
        model = get_model(provider, llm_config=llm_config)

        # Create tool dependencies for injection
        tool_deps = ToolDependencies.create_default()
        model.bill_with_platform_credits = not llm_config.is_user_model()
        model.llm_billing_service = tool_deps.container.llm_billing_service

        # Resolve required tool names based on agent type, model, and tool_args
        agent_tools = AgentToolManager.resolve_tools(
            agent_type=agent_type,
            model_name=model.id,
            tool_args=tool_args,
            dependencies=tool_deps,
        )

        # Add SkillTool if skill creator is available
        if skill_creator is not None:
            skill_tool = await skill_creator.create_skill_tool()
            if skill_tool:
                agent_tools.append(skill_tool)
                logger.info(f"Added SkillTool with {len(skill_tool._skills_registry)} skills")

        # Add connector tools if available
        if connector_tool is not None:
            try:
                connector_tools = await connector_tool.create_connector_tools(
                    workspace_manager=workspace_manager,
                )
                if connector_tools:
                    logger.info(f"[V1 Factory] Received {len(connector_tools)} connector tools from loader")
                    logger.debug(f"[V1 Factory] Connector tool names: {[t.name for t in connector_tools]}")
                    agent_tools.extend(connector_tools)
                    logger.info(f"[V1 Factory] Successfully added {len(connector_tools)} connector tools to agent")

            except Exception as e:
                logger.error(f"[V1 Factory] Failed to load connector tools: {e}", exc_info=True)

        AgentToolManager.log_tool_summary(agent_tools, f"Agent {agent_type.value}")

        # Generate system prompt if not provided
        if system_prompt is None:
            workspace_path = (
                workspace_manager.root.absolute().as_posix() if workspace_manager else "/workspace"
            )

            # Check if A2A agents are available (from metadata or config)
            has_a2a = False  # This would be determined by A2AManager in production

            system_prompt = await get_system_prompt_for_agent_type(
                agent_type=agent_type,
                workspace_path=workspace_path,
                design_document=has_design_doc,
                researcher=has_researcher,
                media=has_media,
                browser=has_browser,
                a2a_agents=has_a2a,
                task_agent=has_task_agent,
                metadata=metadata,
                api_type=llm_config.api_type if llm_config else None,
            )

        sub_agents = []
        if has_task_agent:
            task_agent = await self.create_task_agent_tool(
                user_id=user_id,
                session_id=session_id,
                llm_config=llm_config,
                tool_args=tool_args,
            )
            sub_agents.append(task_agent)

        # Create the agent
        agent = IIAgent(
            user_id=user_id,
            session_id=session_id,
            model=model,
            name=f"{agent_type.value}_agent",
            tools=agent_tools,
            system_message=system_prompt,
            session_store=session_store,
            metadata=metadata,
            sub_agents=sub_agents,
            retries=0,
            stream=True,
            stream_events=True,
            store_events=True
        )

        # Set agent ID
        agent.set_id()

        logger.info(f"Created {agent_type.value} agent with {len(agent_tools)} tools")

        return agent

    def get_agent_config(self, agent_type: AgentType):
        """Get configuration for an agent type.

        Args:
            agent_type: The agent type

        Returns:
            AgentConfig for the type
        """
        return AgentConfigManager.get_config(agent_type)

    # ==================== Sub-Agent Creation Methods ====================

    async def create_task_agent_tool(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        tool_args: Optional[Dict[str, Any]] = None,
        run_id: Optional[UUID] = None,
    ):
        """Create a task agent as a tool for delegation.

        Args:
            llm_client: LLM client instance
            tools: List of loaded tool instances (will be filtered)
            context_manager: Context manager for the agent
            event_stream: Event stream for communication
            max_turns: Maximum conversation turns
            tool_args: Tool configuration arguments
            session_id: Session ID
            run_id: Run ID

        Returns:
            Task agent wrapped as a BaseAgentTool
        """

        logger.info("Creating task agent sub-agent tool")

        provider = PROVIDER_SPEC_MAP.get(llm_config.api_type, Provider.CUSTOM)
        # Resolve model
        model = get_model(provider, llm_config=llm_config)
        # Resolve required tool names
        tool_deps = ToolDependencies.create_default()
        model.bill_with_platform_credits = not llm_config.is_user_model()
        model.llm_billing_service = tool_deps.container.llm_billing_service
        agent_tools = AgentToolManager.resolve_tools(
            agent_type=AgentType.TASK_AGENT,
            model_name=model.id,
            tool_args=tool_args,
            dependencies=tool_deps,
        )

        task_agent = IIAgent(
            user_id=user_id,
            session_id=session_id,
            model=model,
            tools=agent_tools,
            name=TaskAgentTool.name,
            system_message=SYSTEM_PROMPT,
            description=DESCRIPTION,
            stream=True,
            stream_events=True,
            store_events=False,
        )

        # # Wrap in task agent tool
        # task_agent = TaskAgentTool(
        #     agent=task_agent,
        #     session_id=session_id,
        #     run_id=run_id,
        # )

        logger.info(f"Created task agent tool with {len(agent_tools)} tools")
        return task_agent
