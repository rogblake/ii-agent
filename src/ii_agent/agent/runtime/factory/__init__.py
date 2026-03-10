"""Agent factory for creating configured agent instances.

This package provides a clean, maintainable system for creating agents and sub-agents.

Basic usage:
    from ii_agent.agent.runtime.factory import AgentFactory, AgentType

    factory = AgentFactory(config=settings)
    agent = await factory.create_agent(
        user_id="user123",
        session_id="session456",
        llm_config=llm_config,
        all_tools=tools,
        agent_type=AgentType.GENERAL,
    )
"""

from ii_agent.agent.types import AgentType
from ii_agent.agent.runtime.factory.tools import (
    AgentConfig,
    AgentConfigManager,
    AgentToolConfig,
    TOOL_CLASS_MAP,
)
from ii_agent.agent.runtime.factory.factory import AgentFactory
from ii_agent.agent.runtime.factory.tool_manager import AgentToolManager

__all__ = [
    # Factory
    "AgentFactory",
    # Configuration
    "AgentType",
    "AgentConfig",
    "AgentToolConfig",
    "AgentConfigManager",
    "TOOL_CLASS_MAP",
    # Tool management
    "AgentToolManager",
]
