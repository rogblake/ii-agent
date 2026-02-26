"""Service layer for Composio composio domain.

Merges legacy profile_service + integration_mcp_service into a single
stateless service that takes ``db: AsyncSession`` as its first parameter
for every database-touching method.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, TYPE_CHECKING
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.logger import logger
from ii_agent.integrations.connectors.models import ComposioProfile
from ii_agent.core.secrets.encryption import EncryptionManager

from .auth_config_service import AuthConfigService
from .cache_service import ComposioCacheService
from .client import ComposioClient
from .connected_account_service import ConnectedAccountService
from .default_toolkit_tools import get_default_tools
from .mcp_server_service import MCPServerService
from .repository import ComposioProfileRepository
from .schemas import ComposioProfileInfo, ConnectToolkitResponse
from .toolkit_service import ToolkitService

if TYPE_CHECKING:
    from fastapi import Request as HTTPRequest

DEFAULT_REDIRECT_URL = "http://localhost:8000/connectors/callback"


class ComposioService:
    """Business-logic layer for Composio integrations.

    Constructor accepts optional collaborators so that tests can inject fakes.
    A module-level singleton ``composio_service`` is created at import time.
    """

    def __init__(
        self,
        *,
        repo: ComposioProfileRepository,
        config: Settings,
        mcp_setting_service=None,
        toolkit_service: ToolkitService,
        auth_config_service: AuthConfigService,
        connected_account_service: ConnectedAccountService,
        mcp_server_service: MCPServerService,
    ) -> None:
        self._config = config
        self._repo = repo
        self._encryption: Optional[EncryptionManager] = None
        self._mcp_setting_service = mcp_setting_service
        self._toolkit_service = toolkit_service
        self._auth_config_service = auth_config_service
        self._connected_account_service = connected_account_service
        self._mcp_server_service = mcp_server_service

    # -- Encryption helpers --------------------------------------------------

    def _get_encryption(self) -> EncryptionManager:
        if self._encryption is None:
            key = self._config.composio_encryption_key
            if not key:
                raise ValueError(
                    "COMPOSIO_ENCRYPTION_KEY not configured. "
                    "Generate one with: from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())"
                )
            self._encryption = EncryptionManager(key=key)
        return self._encryption

    def _encrypt_mcp_url(self, mcp_url: str) -> str:
        return self._get_encryption().encrypt_raw(mcp_url)

    def _decrypt_mcp_url(self, encrypted_mcp_url: str) -> str:
        return self._get_encryption().decrypt_raw(encrypted_mcp_url)

    # -- Profile name generation ---------------------------------------------

    async def _generate_unique_profile_name(
        self, db: AsyncSession, user_id: str, base_name: str
    ) -> str:
        count = await self._repo.count_profiles_with_name_prefix(db, user_id, base_name)
        if count == 0:
            return base_name
        for i in range(2, count + 10):
            candidate = f"{base_name} ({i})"
            if not await self._repo.profile_name_exists(db, user_id, candidate):
                return candidate
        return f"{base_name} ({count + 2})"

    # -- Model ↔ DTO helpers -------------------------------------------------

    @staticmethod
    def _profile_to_info(profile: ComposioProfile) -> ComposioProfileInfo:
        return ComposioProfileInfo(
            id=profile.id,
            user_id=profile.user_id,
            profile_name=profile.profile_name,
            toolkit_slug=profile.toolkit_slug,
            toolkit_name=profile.toolkit_name,
            status=profile.status,
            is_default=profile.is_default,
            enabled_tools=profile.enabled_tools if profile.enabled_tools else [],
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    # -- Profile CRUD --------------------------------------------------------

    async def create_profile(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        profile_name: str,
        toolkit_slug: str,
        toolkit_name: str,
        mcp_url: str,
        auth_config_id: str,
        connected_account_id: str,
        mcp_server_id: str,
        composio_user_id: str,
        redirect_url: Optional[str] = None,
        is_default: bool = False,
        status: str = "pending",
    ) -> ComposioProfileInfo:
        unique_name = await self._generate_unique_profile_name(db, user_id, profile_name)
        default_tools = get_default_tools(toolkit_slug)

        profile = ComposioProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            profile_name=unique_name,
            toolkit_slug=toolkit_slug,
            toolkit_name=toolkit_name,
            auth_config_id=auth_config_id,
            connected_account_id=connected_account_id,
            mcp_server_id=mcp_server_id,
            composio_user_id=composio_user_id,
            encrypted_mcp_url=self._encrypt_mcp_url(mcp_url),
            redirect_url=redirect_url,
            status=status,
            is_default=is_default,
            enabled_tools=default_tools,
        )

        created = await self._repo.create(db, profile)
        logger.info(f"Created Composio profile: {created.id}")
        return self._profile_to_info(created)

    async def get_profiles(
        self,
        db: AsyncSession,
        user_id: str,
        toolkit_slug: Optional[str] = None,
    ) -> List[ComposioProfileInfo]:
        profiles = await self._repo.get_profiles_by_user(db, user_id, toolkit_slug)
        return [self._profile_to_info(p) for p in profiles]

    async def get_profile(
        self, db: AsyncSession, profile_id: str, user_id: str
    ) -> Optional[ComposioProfile]:
        return await self._repo.get_by_id_and_user(db, profile_id, user_id)

    async def enable_profile(
        self, db: AsyncSession, profile_id: str, user_id: str
    ) -> bool:
        return await self._repo.update_status(db, profile_id, user_id, "enable")

    async def disable_profile(
        self, db: AsyncSession, profile_id: str, user_id: str
    ) -> bool:
        return await self._repo.update_status(db, profile_id, user_id, "disable")

    async def delete_profile(
        self, db: AsyncSession, profile_id: str, user_id: str
    ) -> bool:
        return await self._repo.delete(db, profile_id, user_id)

    async def update_enabled_tools(
        self, db: AsyncSession, profile_id: str, enabled_tools: list
    ) -> bool:
        return await self._repo.update_enabled_tools(db, profile_id, enabled_tools)

    # -- MCP config helpers --------------------------------------------------

    async def get_user_composio_mcp_configs(
        self, db: AsyncSession, user_id: str
    ) -> Dict[str, Dict[str, str]]:
        """Get decrypted MCP configurations for enabled profiles."""
        profiles = await self._repo.get_enabled_profiles_by_user(db, user_id)
        mcp_configs: Dict[str, Dict[str, str]] = {}
        if not profiles:
            return mcp_configs
        try:
            profile = profiles[0]
            decrypted_url = self._decrypt_mcp_url(profile.encrypted_mcp_url)
            mcp_configs["composio"] = {
                "url": decrypted_url,
                "type": "http",
                "headers": {"x-api-key": self._config.composio_api_key},
            }
        except Exception as e:
            logger.error(f"Failed to decrypt MCP URL: {e}", exc_info=True)
        return mcp_configs

    async def get_mcp_config_for_agent(
        self, db: AsyncSession, profile_id: str, user_id: str
    ) -> dict:
        profile = await self._repo.get_by_id_and_user(db, profile_id, user_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")
        mcp_url = self._decrypt_mcp_url(profile.encrypted_mcp_url)
        return {
            "mcpServers": {
                f"composio-{profile.toolkit_slug}": {
                    "url": mcp_url,
                    "transport": "sse",
                }
            },
            "metadata": {
                "tool_type": "composio",
                "toolkit_slug": profile.toolkit_slug,
                "toolkit_name": profile.toolkit_name,
                "profile_id": profile_id,
            },
        }

    async def sync_to_mcp_settings(
        self, db: AsyncSession, profile_id: str, user_id: str
    ):
        """Sync Composio profile to MCP settings for agent consumption."""
        from ii_agent.settings.mcp.schemas import (
            MCPServersConfig,
            ComposioMetadata,
            MCPSettingCreate,
        )
        from fastmcp.mcp_config import RemoteMCPServer

        profile = await self._repo.get_by_id_and_user(db, profile_id, user_id)
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")

        mcp_url = self._decrypt_mcp_url(profile.encrypted_mcp_url)
        server_name = f"composio-{profile.toolkit_slug}"

        mcp_setting_in = MCPSettingCreate(
            mcp_config=MCPServersConfig(
                mcpServers={
                    server_name: RemoteMCPServer(url=mcp_url, transport="sse")
                }
            ),
            metadata=ComposioMetadata(
                tool_type="composio",
                toolkit_slug=profile.toolkit_slug,
                toolkit_name=profile.toolkit_name,
                profile_id=profile_id,
            ),
        )

        mcp_setting = await self._mcp_setting_service.create_mcp_settings(
            db, mcp_setting_in=mcp_setting_in, user_id=user_id
        )
        logger.info(f"Synced profile {profile_id} to MCP settings: {mcp_setting.id}")
        return mcp_setting

    # -- Delete pending cleanup ----------------------------------------------

    async def _delete_pending_profile(
        self,
        db: AsyncSession,
        user_id: str,
        toolkit_slug: str,
    ) -> bool:
        """Delete pending profile for a specific toolkit."""
        profile = await self._repo.find_pending_profile(db, user_id, toolkit_slug)
        if not profile:
            return False
        if profile.connected_account_id:
            try:
                await self._connected_account_service.delete_connected_account(
                    profile.connected_account_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete connected account {profile.connected_account_id}: {e}")
        await self._repo.delete_by_id(db, profile.id)
        logger.info(f"Deleted pending profile for user {user_id}, toolkit: {toolkit_slug}")
        return True

    # -- 6-step integration flow ---------------------------------------------

    async def integrate_toolkit(
        self,
        db: AsyncSession,
        *,
        toolkit_slug: str,
        user_id: str,
        profile_name: str,
        redirect_url: Optional[str] = None,
        initiation_fields: Optional[Dict[str, str]] = None,
        use_custom_auth: bool = False,
        custom_auth_config: Optional[Dict[str, str]] = None,
    ) -> ConnectToolkitResponse:
        """Execute the complete Composio integration flow.

        Steps:
        0. Clean up pending profiles
        1. Verify toolkit exists
        2. Create auth config (reuse if existing)
        3. Create connected account (OAuth)
        4. Create or update MCP server
        5. Save encrypted profile
        """
        composio_user_id = user_id

        # Step 0: clean up pending profiles
        await self._delete_pending_profile(db, user_id, toolkit_slug)

        # Step 1: verify toolkit
        toolkit = await self._toolkit_service.get_toolkit_by_slug(toolkit_slug)
        if not toolkit:
            raise ValueError(f"Toolkit '{toolkit_slug}' not found or doesn't support OAuth2")

        # Step 2: create auth config (reuse existing if found)
        existing_auth_config_id = await self._repo.check_existing_auth_config(db, toolkit_slug)
        auth_config = await self._auth_config_service.create_auth_config(
            toolkit_slug=toolkit_slug,
            initiation_fields=initiation_fields,
            custom_auth_config=custom_auth_config,
            use_custom_auth=use_custom_auth,
            existing_auth_config_id=existing_auth_config_id,
        )

        # Step 3: create connected account
        final_redirect_url = redirect_url or DEFAULT_REDIRECT_URL
        connected_account = await self._connected_account_service.create_connected_account(
            auth_config_id=auth_config.id,
            user_id=composio_user_id,
            initiation_fields=initiation_fields,
            callback_url=final_redirect_url,
        )

        # Step 4: create or update MCP server
        existing_mcp_server_id = await self._repo.get_user_mcp_server_id(db, user_id)
        if existing_mcp_server_id:
            existing_mcp_configs = await self.get_user_composio_mcp_configs(db, user_id)
            if existing_mcp_configs:
                first_config = next(iter(existing_mcp_configs.values()))
                mcp_url_response = first_config["url"]
            else:
                mcp_url_gen = await self._mcp_server_service.generate_mcp_url(
                    mcp_server_id=existing_mcp_server_id,
                    composio_user_id=composio_user_id,
                )
                mcp_url_response = mcp_url_gen.mcp_url
            mcp_server = await self._mcp_server_service.update_mcp_server(
                mcp_server_id=existing_mcp_server_id,
                auth_config_ids=[auth_config.id],
                toolkit_slug=toolkit.get("slug"),
            )
        else:
            mcp_server, mcp_url_response = await self._mcp_server_service.create_mcp_server(
                auth_config_ids=[auth_config.id],
                toolkit_name=toolkit.get("name"),
                toolkit_slug=toolkit.get("slug"),
                allowed_tools=None,
                composio_user_id=composio_user_id,
            )

        # Step 5: save profile
        is_active = connected_account.status == "ACTIVE"
        profile_status = "enable" if is_active else "pending"
        composio_profile = await self.create_profile(
            db,
            user_id=user_id,
            profile_name=profile_name,
            toolkit_slug=toolkit_slug,
            toolkit_name=toolkit.get("name"),
            mcp_url=mcp_url_response,
            auth_config_id=auth_config.id,
            connected_account_id=connected_account.id,
            mcp_server_id=mcp_server.id,
            composio_user_id=composio_user_id,
            redirect_url=connected_account.redirect_url,
            is_default=False,
            status=profile_status,
        )

        message = (
            f"{toolkit.get('name')} connection is active."
            if is_active
            else (
                f"{toolkit.get('name')} connection status is "
                f"'{connected_account.status or 'UNKNOWN'}'. "
                "Complete authorization using the redirect URL."
            )
        )

        return ConnectToolkitResponse(
            success=is_active,
            profile_id=composio_profile.id,
            redirect_url=connected_account.redirect_url or final_redirect_url,
            message=message,
            connection_status=connected_account.status or "UNKNOWN",
        )

    # -- OAuth completion ----------------------------------------------------

    async def complete_oauth(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        app_name: str,
        connected_account_id: str,
    ) -> bool:
        """Mark a pending profile as enabled after OAuth completes."""
        profile = await self._repo.find_profile_by_connected_account(
            db, user_id, app_name, connected_account_id
        )
        if not profile:
            logger.warning(
                f"No profile found for user {user_id}, toolkit {app_name} "
                f"with connected account {connected_account_id}"
            )
            return False
        await self._repo.update_status(db, profile.id, user_id, "enable")
        logger.info(f"Updated profile {profile.id} to connected (account: {connected_account_id})")
        return True

    # -- Update profile tools with MCP sync ----------------------------------

    async def update_profile_tools(
        self,
        db: AsyncSession,
        *,
        profile_id: str,
        user_id: str,
        enabled_tools: List[str],
    ) -> bool:
        """Update enabled tools for a profile and sync with MCP server."""
        from composio_client.types.tool_router_create_session_params import ConfigToolkit

        profile = await self._repo.get_by_id_and_user(db, profile_id, user_id)
        if not profile:
            return False

        await self._repo.update_enabled_tools(db, profile_id, enabled_tools)

        # Sync allowed_tools to MCP server
        try:
            all_profiles = await self._repo.get_profiles_by_mcp_server(
                db, user_id, profile.mcp_server_id
            )
            all_allowed_tools: set = set()
            for p in all_profiles:
                if p.id == profile_id:
                    all_allowed_tools.update(enabled_tools)
                else:
                    all_allowed_tools.update(p.enabled_tools or [])

            final_allowed_tools = list(all_allowed_tools) if all_allowed_tools else None

            current_server = await self._mcp_server_service.get_mcp_server(profile.mcp_server_id)
            if current_server:
                toolkit_configs: Dict[str, str] = {}
                for p in all_profiles:
                    if p.toolkit_slug not in toolkit_configs:
                        toolkit_configs[p.toolkit_slug] = p.auth_config_id
                toolkits = []
                for tk_slug, auth_id in toolkit_configs.items():
                    tk_config = ConfigToolkit(toolkit=tk_slug)
                    tk_config["auth_config"] = auth_id
                    toolkits.append(tk_config)
                self._mcp_server_service._call_mcp_update(
                    profile.mcp_server_id, toolkits, final_allowed_tools
                )
        except Exception as e:
            logger.warning(f"Failed to update MCP server allowed_tools: {e}", exc_info=True)

        return True

    # -- Toolkit discovery delegates -----------------------------------------

    async def list_toolkits(
        self, search: Optional[str] = None, category: Optional[str] = None, limit: int = 100
    ):
        if search:
            return await self._toolkit_service.search_toolkits(search, category, limit)
        return await self._toolkit_service.list_toolkits(limit=limit, category=category)

    async def get_toolkit_details(self, toolkit_slug: str):
        return await self._toolkit_service.get_detailed_toolkit_info(toolkit_slug)

    async def get_toolkit_actions(self, toolkit_slug: str):
        """Get available actions for a toolkit with categories."""
        cached_actions = await ComposioCacheService.get_toolkit_actions(toolkit_slug)
        if cached_actions and cached_actions.get("actions"):
            cached_actions["actions"] = [
                {k: v for k, v in action.items() if k != "parameters"}
                for action in cached_actions["actions"]
            ]
            return cached_actions

        client = ComposioClient.get_client()
        actions = client.tools.get_raw_composio_tools(toolkits=[toolkit_slug], limit=1000)

        def extract_category(item):
            slug = item.slug or ""
            parts = slug.split("_")
            return parts[1] if len(parts) > 1 else "OTHER"

        default_tool_slugs = set(get_default_tools(toolkit_slug))
        excepted_actions = ToolkitService.EXCEPT_TOOLKIT.get(toolkit_slug, [])

        categories: set = set()
        formatted_actions = []
        for action in actions:
            action_slug = action.slug or "unknown_action"
            if action_slug in excepted_actions:
                continue
            category = extract_category(action)
            if not category and hasattr(action, "tags") and action.tags:
                category = action.tags[0]
            categories.add(category)
            formatted_actions.append(
                {
                    "name": action_slug,
                    "description": action.description or "",
                    "category": category,
                    "read_only": "read" in action_slug.lower() or "get" in action_slug.lower(),
                    "display_name": action_slug,
                    "default_enabled": action_slug in default_tool_slugs,
                    "parameters": action.input_parameters or {},
                }
            )

        actions_without_params = [
            {k: v for k, v in a.items() if k != "parameters"} for a in formatted_actions
        ]
        result = {
            "success": True,
            "actions": actions_without_params,
            "categories": sorted(categories),
        }
        await ComposioCacheService.set_toolkit_actions(
            toolkit_slug,
            actions_data=formatted_actions,
            categories=sorted(categories),
        )
        return result

    # -- Callback URL helper -------------------------------------------------

    def resolve_callback_url(self, http_request: "HTTPRequest") -> str:
        """Determine the OAuth callback URL from config or request headers."""
        if self._config.composio_redirect_uri:
            return self._config.composio_redirect_uri
        frontend_origin = None
        referer = http_request.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
        if not frontend_origin:
            frontend_origin = f"{http_request.url.scheme}://{http_request.url.netloc}"
        return f"{frontend_origin}/auth/oauth/composio/callback"
