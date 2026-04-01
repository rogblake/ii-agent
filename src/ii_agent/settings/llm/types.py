"""LLM settings domain enums."""

from enum import StrEnum


class Provider(StrEnum):
    """LLM provider identifier.

    Single source of truth — imported by settings/llm models, agent models,
    billing/credits, and any module that needs provider discrimination.
    """

    OPENAI = "OpenAI"
    ANTHROPIC = "Anthropic"
    VERTEX_AI = "VertexAI"
    GOOGLE = "Google"
    AZURE = "Azure"
    CEREBRAS = "Cerebras"
    CUSTOM = "Custom"


class ConfigType(StrEnum):
    """Discriminator for system vs user LLM settings."""

    USER = "user"
    SYSTEM = "system"
