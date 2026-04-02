from __future__ import annotations
from typing import Dict

from pydantic import (
    BaseModel,
    Field,
)

from ii_agent.core.config.llm_config import LLMConfig


class PersistedSettings(BaseModel):
    """
    Persisted settings for II_AGENT sessions
    """

    llm_configs: Dict[str, LLMConfig] = Field(default_factory=dict)

    model_config = {
        "validate_assignment": True,
    }
