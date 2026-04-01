"""Backward compatiblity tools from V0, will remove it later.

This package provides a clean, maintainable system for creating agents and sub-agents.

Basic usage:
    from ii_agent.agents import AgentFactory, AgentType
    from ii_agent.core.config.settings import get_settings

    factory = AgentFactory(get_settings())
    agent = await factory.create_agent(
        user_id="user123",
        session_id="session456",
        llm_config=llm_config,
        all_tools=tools,
        agent_type=AgentType.GENERAL,
    )
"""

from ii_agent.agents.factory.tools import (
    AgentConfig,
    AgentConfigManager,
    AgentToolConfig,
    AgentType,
    TOOL_CLASS_MAP,
)
from ii_agent.agents.factory.agent import AgentFactory, agent_factory
from ii_agent.agents.factory.tool_manager import AgentToolManager

__all__ = [
    # Main agent class
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
    "agent_factory",
]
