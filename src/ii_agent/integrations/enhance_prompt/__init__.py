"""Enhance prompt integration module.

Provides prompt enhancement via external LLM providers.
No database models -- this is a stateless integration.

Import pattern:
    from ii_agent.integrations.enhance_prompt import router
    from ii_agent.integrations.enhance_prompt import create_enhance_prompt_client
"""

from .client import create_enhance_prompt_client
from .router import router

__all__ = [
    "create_enhance_prompt_client",
    "router",
]
