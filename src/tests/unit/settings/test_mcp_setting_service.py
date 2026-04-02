from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.settings.mcp.exceptions import MCPOAuthError
from ii_agent.settings.mcp.schemas import MCPServersConfig
from ii_agent.settings.mcp.service import MCPSettingService


class FakeMCPRepo:
    def __init__(self):
        self.active = []
        self.created = []
        self.updated = []
        self.by_tool = {}

    async def list_active_by_user(self, db, user_id):
        return self.active

    async def update(self, db, setting):
        self.updated.append(setting)
        return setting

    async def create(self, db, setting):
        self.created.append(setting)
        return setting

    async def get_by_user_and_tool_type(self, db, user_id, tool_type):
        return self.by_tool.get(tool_type)

    async def get_by_id_and_user(self, db, setting_id, user_id):
        return None

    async def list_by_user(self, db, user_id, only_active=False, no_metadata=False):
        return []

    async def delete(self, db, setting):
        return None


@pytest.mark.asyncio
async def test_create_mcp_settings_deactivates_previous_active(settings_factory):
    active_setting = SimpleNamespace(is_active=True, updated_at=None)
    repo = FakeMCPRepo()
    repo.active = [active_setting]

    service = MCPSettingService(repo=repo, config=settings_factory())

    result = await service.create_mcp_settings(
        db=None,
        user_id="u1",
        mcp_setting_in=SimpleNamespace(
            mcp_config=MCPServersConfig(mcpServers={}),
            metadata=None,
        ),
    )

    assert active_setting.is_active is False
    assert len(repo.created) == 1
    assert result.is_active is True


@pytest.mark.asyncio
async def test_configure_codex_requires_auth_or_api_key(settings_factory):
    service = MCPSettingService(repo=FakeMCPRepo(), config=settings_factory())

    with pytest.raises(MCPOAuthError):
        await service.configure_codex(
            db=None,
            user_id="u1",
            auth_json=None,
            apikey=None,
            model=None,
            reasoning_effort=None,
            search=False,
        )


@pytest.mark.asyncio
async def test_configure_claude_code_validates_authorization_format(settings_factory):
    service = MCPSettingService(repo=FakeMCPRepo(), config=settings_factory())

    with pytest.raises(MCPOAuthError, match="Invalid authorization code format"):
        await service.configure_claude_code(
            db=None,
            user_id="u1",
            authorization_code="invalid-format",
        )
