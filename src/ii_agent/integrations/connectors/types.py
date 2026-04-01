"""Connectors domain enums."""

from enum import StrEnum


class ConnectorType(StrEnum):
    """External service connector types."""

    GOOGLE_DRIVE = "google_drive"
    GITHUB = "github"
    REVENUECAT = "revenuecat"
    CHATGPT_MCP = "chatgpt_mcp"
    COMPOSIO = "composio"


class ComposioProfileStatus(StrEnum):
    """Status of a Composio profile connection."""

    ENABLE = "enable"
    DISABLE = "disable"
    DISCONNECTED = "disconnected"
    PENDING = "pending"
