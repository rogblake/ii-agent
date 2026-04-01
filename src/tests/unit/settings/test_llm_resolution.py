import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.settings.llm.service import ModelSettingService, get_system_llm_config_from_db

U1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
S1 = uuid.UUID("00000000-0000-0000-0000-000000000011")


class FakeRepo:
    async def get_by_model_and_user(self, db, model_id, user_id):
        return None

    async def get_by_id_and_user(self, db, model_id, user_id):
        return None

    async def list_by_user(self, db, user_id, provider=None, config_type=None):
        return []

    async def get_system_by_model(self, db, model_id):
        return None


class FakeSessionRepo:
    def __init__(self, session):
        self.session = session

    async def get_by_id(self, db, session_id):
        return self.session


@pytest.mark.asyncio
async def test_get_llm_settings_prefers_user_source_when_requested():
    service = ModelSettingService(
        repo=FakeRepo(),
        session_repo=FakeSessionRepo(session=SimpleNamespace(llm_setting_id=None)),
    )

    async def _user_config(db, model_id, user_id):
        return LLMConfig(
            setting_id="user-setting",
            model="gpt-4o",
            api_type=APITypes.OPENAI,
            config_type="user",
        )

    service.get_user_llm_config = _user_config

    llm = await service.get_llm_settings(
        db=None,
        session=SimpleNamespace(id=S1, user_id=U1),
        source="user",
        model_id="gpt-4o",
    )

    assert llm.config_type == "user"


@pytest.mark.asyncio
async def test_get_llm_settings_falls_back_to_system_when_user_setting_missing():
    service = ModelSettingService(
        repo=FakeRepo(),
        session_repo=FakeSessionRepo(session=SimpleNamespace(llm_setting_id="sys-setting")),
    )

    async def _missing_user_config(db, model_id, user_id):
        raise ValueError("missing")

    service.get_user_llm_config = _missing_user_config

    # Mock resolve_config_by_setting_id to return system config
    service.resolve_config_by_setting_id = AsyncMock(
        return_value=LLMConfig(
            model="gpt-4o",
            api_type=APITypes.OPENAI,
            config_type="system",
            setting_id="sys-setting",
        )
    )

    llm = await service.get_llm_settings(
        db=None,
        session=SimpleNamespace(id=S1, user_id=U1),
    )

    assert llm.config_type == "system"
    assert llm.setting_id == "sys-setting"


@pytest.mark.asyncio
async def test_get_system_llm_config_from_db_raises_for_missing_model(monkeypatch):
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.LLMSettingRepository.get_system_by_model",
        AsyncMock(return_value=None),
    )
    with pytest.raises(ValueError):
        await get_system_llm_config_from_db(db=None, model_id="missing")
