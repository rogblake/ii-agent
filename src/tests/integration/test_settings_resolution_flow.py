from types import SimpleNamespace

import pytest

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.settings.llm.service import ModelSettingService

pytestmark = pytest.mark.integration


class LLMRepo:
    pass


class SessionRepo:
    def __init__(self, llm_setting_id=None):
        self.session = SimpleNamespace(llm_setting_id=llm_setting_id)

    async def get_by_id(self, db, session_id):
        return self.session


@pytest.mark.asyncio
async def test_settings_resolution_user_then_system_fallback(settings_factory, monkeypatch):
    system_cfg = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)

    service = ModelSettingService(
        repo=LLMRepo(),
        config=settings_factory(llm_configs={"system-model": system_cfg}),
        session_repo=SessionRepo(llm_setting_id="system-model"),
    )

    async def _missing_user(*args, **kwargs):
        raise ValueError("missing")

    monkeypatch.setattr(service, "get_user_llm_config", _missing_user)

    resolved = await service.get_llm_settings(
        db=None,
        session=SimpleNamespace(id="s1", user_id="u1"),
    )

    assert resolved.config_type == "system"
    assert resolved.setting_id == "system-model"
