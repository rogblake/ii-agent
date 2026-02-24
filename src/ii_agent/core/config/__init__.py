"""Configuration module for ii_agent.

This module exports configuration classes and the cached get_settings() factory.

The configuration is organized into modular sections:
- DatabaseSettings: Database configuration
- RedisSettings: Redis caching and sessions
- SandboxSettings: Sandbox environment configuration
- StorageSettings: File storage configuration
- OAuth2Settings: OAuth provider configurations
- MCPSettings: MCP protocol configuration
- StripeSettings: Billing configuration
- CreditsSettings: Credits and subscriptions
- AgentSettings: Agent execution configuration
- MobileSettings: Mobile and Apple integration configuration
- EnhancePromptConfig: Enhance prompt configuration
- Settings: Main settings class (consolidates all above)
"""

# New modular configuration
from ii_agent.core.config.settings import (
    Settings,
    get_settings,
    II_AGENT_DIR,
)
from ii_agent.core.config.database import DatabaseSettings
from ii_agent.core.config.redis import RedisSettings
from ii_agent.core.config.sandbox import SandboxSettings, SandboxProvider, DEFAULT_SANDBOX_TIMEOUT_SECONDS
from ii_agent.core.config.storage import StorageSettings, StorageProvider
from ii_agent.core.config.oauth import OAuth2Settings
from ii_agent.core.config.mcp import MCPSettings
from ii_agent.core.config.stripe import StripeSettings
from ii_agent.core.config.credits import CreditsSettings
from ii_agent.core.config.agent import AgentSettings
from ii_agent.core.config.mobile import MobileSettings
from ii_agent.core.config.enhance_prompt_config import EnhancePromptConfig

# LLMConfig and ResearcherAgentConfig are lazy-loaded to avoid circular imports
# (llm_config.py -> utils.constants -> ... -> core.db.base -> settings.py)

_LAZY_IMPORTS = {
    "LLMConfig": "ii_agent.core.config.llm_config",
    "ResearcherAgentConfig": "ii_agent.core.config.llm_config",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib
        module = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Main settings
    "Settings",
    "get_settings",
    # Modular settings
    "DatabaseSettings",
    "RedisSettings",
    "SandboxSettings",
    "StorageSettings",
    "OAuth2Settings",
    "MCPSettings",
    "StripeSettings",
    "CreditsSettings",
    "AgentSettings",
    "MobileSettings",
    "EnhancePromptConfig",
    # Type aliases
    "SandboxProvider",
    "StorageProvider",
    # Constants
    "DEFAULT_SANDBOX_TIMEOUT_SECONDS",
    "II_AGENT_DIR",
    # Legacy (lazy-loaded)
    "LLMConfig",
    "ResearcherAgentConfig",
]
