"""Tool management for agents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ii_agent.engine.types import AgentType
from ii_agent.engine.v1.factory.tools import COMMON_TOOLS, TOOL_CLASS_MAP, TOOL_CONFIRM_MAP, AgentConfigManager
from ii_agent.engine.v1.tools.mcp import MCPTool
from ii_agent.engine.v1.tools.base import BaseAgentTool
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.engine.v1.tools.dependencies import ToolDependencies

class AgentToolManager:
    """Manages tool selection and configuration for agents."""

    @staticmethod
    def resolve_tools(
        agent_type: AgentType,
        model_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        include_mcp: str = True,
        include_connector: str = True,
        dependencies: Optional[ToolDependencies] = None,
    ) -> List[BaseAgentTool]:
        """Resolve required tool names for an agent.

        This method determines which tools are needed based on:
        1. Core tools from agent type configuration
        2. Model-specific include/exclude rules
        3. Additional tools based on tool_args (media, browser, etc.)

        Args:
            agent_type: The agent type
            model_name: Optional model name for model-specific filtering
            tool_args: Tool configuration arguments (media_generation, browser, etc.)
            dependencies: Optional tool dependencies to inject into tools

        Returns:
            List of required tool names for the agent
        """
        tool_args = tool_args or {}

        # Get flags from tool_args
        include_media = tool_args.get("media_generation", False)
        include_browser = tool_args.get("browser", False)

        # Get required tool names from configuration
        # This handles: core tools + model filtering + media/browser additions
        required_tool_names = AgentConfigManager.get_tools_for_agent(
            agent_type=agent_type,
            model_name=model_name,
            tool_args=tool_args,
        )
        all_tools = []
        for tool_name in required_tool_names:
            new_tool = AgentToolManager.convert_tool(tool_name, dependencies=dependencies)
            if new_tool:
                all_tools.append(new_tool)

        common_tools = AgentToolManager._get_common_tools(dependencies=dependencies)
        all_tools.extend(common_tools)

        logger.info(
            f"Agent {agent_type.value} requires {len(required_tool_names)} tools "
            f"(media={include_media}, browser={include_browser}, model={model_name or 'default'})"
        )
        logger.debug(f"Required tools: {', '.join(sorted(required_tool_names))}")
        return all_tools

    @staticmethod
    def _get_common_tools(
        dependencies: Optional[ToolDependencies] = None,
    ) -> List[BaseAgentTool]:
        _tools = []
        for tool in COMMON_TOOLS:
            instance = tool()
            if dependencies is not None:
                instance.dependencies = dependencies
            _tools.append(instance)
        return _tools

    @staticmethod
    def convert_mcp_tool(tool_name: str) -> MCPTool | None:
        tool_class = TOOL_CLASS_MAP.get(tool_name)
        if not tool_class:
            return None
        requires_confirmation = TOOL_CONFIRM_MAP.get(tool_name, False)
        return MCPTool(
            name=tool_class.name,
            description=tool_class.description,
            input_schema=tool_class.input_schema,
            read_only=tool_class.read_only,
            display_name=tool_class.display_name,
            requires_confirmation=requires_confirmation,
        )

    @staticmethod
    def convert_tool(
        tool_name: str,
        dependencies: Optional[ToolDependencies] = None,
    ) -> BaseAgentTool | None:
        tool_class = TOOL_CLASS_MAP.get(tool_name)
        if not tool_class:
            return None
        requires_confirmation = TOOL_CONFIRM_MAP.get(tool_name, False)
        if issubclass(tool_class, MCPTool):
            instance = tool_class(
                name=tool_class.name,
                description=tool_class.description,
                input_schema=tool_class.input_schema,
                read_only=tool_class.read_only,
                display_name=tool_class.display_name,
                requires_confirmation=requires_confirmation
            )
            if dependencies is not None:
                instance.dependencies = dependencies
            return instance
        elif issubclass(tool_class, BaseAgentTool):
            instance = tool_class()
            if dependencies is not None:
                instance.dependencies = dependencies
            return instance
        return None

    @staticmethod
    def validate_tools(tools: List[BaseAgentTool]) -> List[BaseAgentTool]:
        """Validate and log tool information.

        Args:
            tools: List of tools to validate

        Returns:
            Validated tools list
        """
        if not tools:
            logger.warning("No tools provided to validate")
            return []

        valid_tools = []
        for tool in tools:
            if not hasattr(tool, "name"):
                logger.warning(f"Tool missing 'name' attribute: {tool}")
                continue

            valid_tools.append(tool)

        logger.info(f"Validated {len(valid_tools)} tools")
        return valid_tools

    @staticmethod
    def log_tool_summary(tools: List[BaseAgentTool], context: str = ""):
        """Log a summary of available tools.

        Args:
            tools: List of tools
            context: Optional context string for the log message
        """
        if not tools:
            logger.info(f"{context}: No tools available")
            return

        logger.info(f"{context}: {len(tools)} tools total")
