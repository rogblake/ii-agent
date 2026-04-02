from types import SimpleNamespace

import pytest

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.settings.llm.service import LLMSettingService, get_system_llm_config


class FakeRepo:
    async def get_by_model_and_user(self, db, model, user_id):
        return None

    async def get_by_id_and_user(self, db, model_id, user_id):
        return None

    async def list_by_user(self, db, user_id, api_type=None):
        return []


class FakeSessionRepo:
    def __init__(self, session):
        self.session = session

    async def get_by_id(self, db, session_id):
        return self.session


@pytest.mark.asyncio
async def test_get_llm_settings_prefers_user_source_when_requested(settings_factory, monkeypatch):
    service = LLMSettingService(
        repo=FakeRepo(),
        config=settings_factory(),
        session_repo=FakeSessionRepo(session=SimpleNamespace(llm_setting_id=None)),
    )

    async def _user_config(db, model_id, user_id):
        return LLMConfig(
            setting_id="user-setting",
            model="gpt-4o",
            api_type=APITypes.OPENAI,
            config_type="user",
        )

    monkeypatch.setattr(service, "get_user_llm_config", _user_config)

    llm = await service.get_llm_settings(
        db=None,
        session=SimpleNamespace(id="s1", user_id="u1"),
        source="user",
        model_id="gpt-4o",
    )

    assert llm.config_type == "user"


@pytest.mark.asyncio
async def test_get_llm_settings_falls_back_to_system_when_user_setting_missing(settings_factory, monkeypatch):
    system_config = LLMConfig(model="gpt-4o", api_type=APITypes.OPENAI)
    service = LLMSettingService(
        repo=FakeRepo(),
        config=settings_factory(llm_configs={"sys-setting": system_config}),
        session_repo=FakeSessionRepo(session=SimpleNamespace(llm_setting_id="sys-setting")),
    )

    async def _missing_user_config(db, model_id, user_id):
        raise ValueError("missing")

    monkeypatch.setattr(service, "get_user_llm_config", _missing_user_config)

    llm = await service.get_llm_settings(
        db=None,
        session=SimpleNamespace(id="s1", user_id="u1"),
    )

    assert llm.config_type == "system"
    assert llm.setting_id == "sys-setting"


def test_get_system_llm_config_raises_for_missing_model(settings_factory):
    with pytest.raises(ValueError):
        get_system_llm_config(model_id="missing", config=settings_factory(llm_configs={}))
