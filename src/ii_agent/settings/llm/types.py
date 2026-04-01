"""LLM settings domain enums."""

from enum import StrEnum


class ConfigType(StrEnum):
    """Discriminator for system vs user LLM settings."""

    USER = "user"
    SYSTEM = "system"
