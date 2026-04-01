"""Enhance prompt integration module.

Provides prompt enhancement via external LLM providers.
No database models -- this is a stateless integration.
"""

from .client import create_enhance_prompt_client

__all__ = [
    "create_enhance_prompt_client",
]
