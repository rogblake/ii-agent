"""Pydantic schemas (DTOs) for Composio composio domain."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


# ---- Request DTOs ----

class ConnectToolkitRequest(BaseModel):
    """Request to connect a Composio toolkit."""
    profile_name: str
    initiation_fields: Optional[dict] = None
    use_custom_auth: bool = False
    custom_auth_config: Optional[dict] = None


class CompleteOAuthRequest(BaseModel):
    """Request to complete OAuth flow."""
    status: str
    connectedAccountId: str
    appName: str


class UpdateProfileToolsRequest(BaseModel):
    """Request to update enabled tools for a profile."""
    enabled_tools: List[str] = []


# ---- Response DTOs ----

class ConnectToolkitResponse(BaseModel):
    """Response from toolkit connection."""
    success: bool
    profile_id: str
    redirect_url: str
    message: str
    connection_status: str


class ToolkitStatusResponse(BaseModel):
    """Toolkit connection status response."""
    status: str  # Values: 'enable', 'disable', 'disconnected', 'pending'
    connector_type: str
    toolkit_slug: str
    profiles: List[dict]


class ProfileMCPConfigResponse(BaseModel):
    """MCP configuration response."""
    mcpServers: dict
    metadata: dict


class SyncProfileResponse(BaseModel):
    """Profile sync response."""
    success: bool
    mcp_setting_id: str
    message: str


class ComposioProfileInfo(BaseModel):
    """Profile information returned to API."""
    id: str
    user_id: str
    profile_name: str
    toolkit_slug: str
    toolkit_name: str
    status: str  # Values: 'enable', 'disable', 'disconnected', 'pending'
    is_default: bool
    enabled_tools: list
    created_at: datetime
    updated_at: datetime
