"""Composio connector API endpoints.

Route ordering: static paths first, then parameterized paths to avoid
path-parameter capture of literal segments.
"""

import uuid
from typing import Optional, List

from fastapi import APIRouter, Query, Request as HTTPRequest

from ii_agent.core.logger import logger
from ii_agent.core.exceptions import ValidationError
from ii_agent.auth.dependencies import CurrentUser
from ii_agent.core.dependencies import DBSession
from ii_agent.integrations.connectors.composio.exceptions import (
    ComposioProfileNotFoundError,
    ComposioToolkitNotFoundError,
    ComposioOAuthError,
)
from ii_agent.integrations.connectors.composio.dependencies import ComposioServiceDep
from ii_agent.integrations.connectors.composio.schemas import (
    ConnectToolkitRequest,
    ConnectToolkitResponse,
    CompleteOAuthRequest,
    ToolkitStatusResponse,
    ProfileMCPConfigResponse,
    SyncProfileResponse,
    UpdateProfileToolsRequest,
)
from ii_agent.integrations.connectors.composio.connected_account_service import ConnectedAccountService

router = APIRouter(prefix="/composio", tags=["composio"])


# ---- Static-path routes (register BEFORE parameterised routes) ----


# 1. GET /connectors/composio/toolkits
@router.get("/toolkits")
async def list_composio_toolkits(
    current_user: CurrentUser,
    svc: ComposioServiceDep,
    search: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(default=100, le=200),
):
    """List available Composio toolkits with OAuth2 support."""
    return await svc.list_toolkits(search=search, category=category, limit=limit)


# 2. GET /connectors/composio/profiles
@router.get("/profiles")
async def list_composio_profiles(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    toolkit_slug: Optional[str] = None,
):
    """List user's Composio profiles."""
    profiles = await svc.get_profiles(db, current_user.id, toolkit_slug)
    return {"profiles": [p.model_dump() for p in profiles]}


# 3. POST /connectors/composio/oauth-complete
@router.post("/oauth-complete")
async def complete_oauth_flow(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    request: CompleteOAuthRequest,
):
    """Complete OAuth flow - called by frontend after OAuth redirect."""
    if request.status != "success":
        raise ComposioOAuthError("OAuth flow failed")

    updated = await svc.complete_oauth(
        db,
        user_id=current_user.id,
        app_name=request.appName,
        connected_account_id=request.connectedAccountId,
    )
    if not updated:
        logger.warning(
            f"No profile found for user {current_user.id}, "
            f"app {request.appName}, account {request.connectedAccountId}"
        )
    return {"success": True, "message": "OAuth flow completed successfully"}


# ---- Toolkit sub-routes (parameterised by toolkit_slug) ----


# 4. GET /connectors/composio/toolkits/{toolkit_slug}
@router.get("/toolkits/{toolkit_slug}")
async def get_toolkit_details(
    current_user: CurrentUser,
    svc: ComposioServiceDep,
    toolkit_slug: str,
):
    """Get detailed toolkit information including auth requirements."""
    details = await svc.get_toolkit_details(toolkit_slug)
    if not details:
        raise ComposioToolkitNotFoundError(f"Toolkit '{toolkit_slug}' not found")
    return details


# 5. GET /connectors/composio/toolkits/{toolkit_slug}/actions
@router.get("/toolkits/{toolkit_slug}/actions")
async def get_toolkit_actions(
    current_user: CurrentUser,
    svc: ComposioServiceDep,
    toolkit_slug: str,
):
    """Get available actions/tools for a toolkit."""
    return await svc.get_toolkit_actions(toolkit_slug)


# 6. POST /connectors/composio/{toolkit_slug}/connect
@router.post("/{toolkit_slug}/connect", response_model=ConnectToolkitResponse)
async def connect_composio_toolkit(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    toolkit_slug: str,
    request: ConnectToolkitRequest,
    http_request: HTTPRequest,
):
    """Start the Composio connection flow for a toolkit."""
    try:
        callback_url = svc.resolve_callback_url(http_request)
        return await svc.integrate_toolkit(
            db,
            toolkit_slug=toolkit_slug,
            user_id=current_user.id,
            profile_name=request.profile_name,
            redirect_url=callback_url,
            initiation_fields=request.initiation_fields,
            use_custom_auth=request.use_custom_auth,
            custom_auth_config=request.custom_auth_config,
        )
    except ValueError as e:
        raise ComposioOAuthError(str(e)) from e


# 7. GET /connectors/composio/{toolkit_slug}/status
@router.get("/{toolkit_slug}/status", response_model=ToolkitStatusResponse)
async def get_composio_status(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    toolkit_slug: str,
):
    """Check connection status for a toolkit."""
    profiles = await svc.get_profiles(db, current_user.id, toolkit_slug)
    connected_profiles = [p.model_dump() for p in profiles if p.status == "enable"]
    if any(p.status == "enable" for p in profiles):
        overall_status = "enable"
    elif any(p.status == "disconnected" for p in profiles):
        overall_status = "disconnected"
    else:
        overall_status = "disable"
    return ToolkitStatusResponse(
        status=overall_status,
        connector_type="composio",
        toolkit_slug=toolkit_slug,
        profiles=connected_profiles,
    )


# 8. DELETE /connectors/composio/{toolkit_slug}
@router.delete("/{toolkit_slug}")
async def disconnect_composio_toolkit(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    toolkit_slug: str,
    profile_id: Optional[uuid.UUID] = None,
):
    """Disconnect Composio toolkit (delete profile and connected account)."""
    if not profile_id:
        raise ValidationError("profile_id query parameter is required")
    profile = await svc.get_profile(db, profile_id, current_user.id)
    if not profile:
        raise ComposioProfileNotFoundError("Profile not found")
    connected_account_service = ConnectedAccountService()
    try:
        await connected_account_service.delete_connected_account(profile.connected_account_id)
    except Exception as e:
        logger.warning(f"Failed to delete connected account from Composio: {e}")
    deleted = await svc.delete_profile(db, profile_id, current_user.id)
    if not deleted:
        raise ComposioProfileNotFoundError("Profile not found")
    return {"success": True, "message": "Toolkit disconnected"}


# ---- Profile sub-routes (/connectors/composio/profiles/{profile_id}/...) ----


# 9. GET /connectors/composio/profiles/{profile_id}/mcp-config
@router.get("/profiles/{profile_id}/mcp-config", response_model=ProfileMCPConfigResponse)
async def get_profile_mcp_config(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    profile_id: uuid.UUID,
):
    """Get MCP configuration for agent integration."""
    try:
        mcp_config = await svc.get_mcp_config_for_agent(db, profile_id, current_user.id)
        return ProfileMCPConfigResponse(**mcp_config)
    except ValueError as e:
        raise ComposioProfileNotFoundError(str(e)) from e


# 10. POST /connectors/composio/profiles/{profile_id}/sync-to-agent
@router.post("/profiles/{profile_id}/sync-to-agent", response_model=SyncProfileResponse)
async def sync_profile_to_agent(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    profile_id: uuid.UUID,
):
    """Sync Composio profile to user's MCP settings for agent use."""
    try:
        mcp_setting = await svc.sync_to_mcp_settings(db, profile_id, current_user.id)
        return SyncProfileResponse(
            success=True,
            mcp_setting_id=mcp_setting.id,
            message="Profile synced to agent MCP settings",
        )
    except ValueError as e:
        raise ComposioProfileNotFoundError(str(e)) from e


# 11. DELETE /connectors/composio/profiles/{profile_id}
@router.delete("/profiles/{profile_id}")
async def delete_composio_profile(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    profile_id: uuid.UUID,
):
    """Delete a specific Composio profile."""
    profile = await svc.get_profile(db, profile_id, current_user.id)
    if not profile:
        raise ComposioProfileNotFoundError("Profile not found")
    connected_account_service = ConnectedAccountService()
    try:
        await connected_account_service.delete_connected_account(profile.connected_account_id)
    except Exception as e:
        logger.warning(f"Failed to delete connected account from Composio: {e}")
    deleted = await svc.delete_profile(db, profile_id, current_user.id)
    if not deleted:
        raise ComposioProfileNotFoundError("Profile not found")
    return {"success": True, "message": "Profile deleted"}


# 12. POST /connectors/composio/profiles/{profile_id}/enable
@router.post("/profiles/{profile_id}/enable")
async def enable_composio_profile(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    profile_id: uuid.UUID,
):
    """Enable a Composio profile and its connected account."""
    profile = await svc.get_profile(db, profile_id, current_user.id)
    if not profile:
        raise ComposioProfileNotFoundError("Profile not found")
    connected_account_service = ConnectedAccountService()
    try:
        await connected_account_service.enable_connected_account(profile.connected_account_id)
    except Exception as e:
        logger.warning(f"Failed to enable connected account in Composio: {e}")
    updated = await svc.enable_profile(db, profile_id, current_user.id)
    if not updated:
        raise ComposioProfileNotFoundError("Profile not found")
    return {"success": True, "message": "Profile enabled"}


# 13. POST /connectors/composio/profiles/{profile_id}/disable
@router.post("/profiles/{profile_id}/disable")
async def disable_composio_profile(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    profile_id: uuid.UUID,
):
    """Disable a Composio profile and its connected account."""
    profile = await svc.get_profile(db, profile_id, current_user.id)
    if not profile:
        raise ComposioProfileNotFoundError("Profile not found")
    connected_account_service = ConnectedAccountService()
    try:
        await connected_account_service.disable_connected_account(profile.connected_account_id)
    except Exception as e:
        logger.warning(f"Failed to disable connected account in Composio: {e}")
    updated = await svc.disable_profile(db, profile_id, current_user.id)
    if not updated:
        raise ComposioProfileNotFoundError("Profile not found")
    return {"success": True, "message": "Profile disabled"}


# 14. PUT /connectors/composio/profiles/{profile_id}/tools
@router.put("/profiles/{profile_id}/tools")
async def update_profile_tools(
    current_user: CurrentUser,
    db: DBSession,
    svc: ComposioServiceDep,
    profile_id: str,
    request: UpdateProfileToolsRequest,
):
    """Update enabled tools for a profile and sync with MCP server."""
    updated = await svc.update_profile_tools(
        db,
        profile_id=profile_id,
        user_id=current_user.id,
        enabled_tools=request.enabled_tools,
    )
    if not updated:
        raise ComposioProfileNotFoundError("Profile not found")
    return {"success": True, "message": f"Updated {len(request.enabled_tools)} enabled tools"}
