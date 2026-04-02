import pytest

from ii_agent.settings.llm.schemas import ModelSettingCreate, ModelSettingUpdate
from ii_agent.settings.llm.service import ModelSettingService


class FakeLLMRepo:
    def __init__(self):
        self.items = {}

    async def get_by_model_and_user(self, db, model_id, user_id):
        return self.items.get((model_id, user_id))

    async def create(self, db, setting):
        self.items[(setting.model_id, setting.user_id)] = setting
        return setting

    async def update(self, db, setting):
        self.items[(setting.model_id, setting.user_id)] = setting
        return setting

    async def get_by_id_and_user(self, db, model_id, user_id):
        for setting in self.items.values():
            if setting.id == model_id and setting.user_id == user_id:
                return setting
        return None

    async def list_by_user(self, db, user_id, provider=None, config_type=None):
        settings = [s for s in self.items.values() if s.user_id == user_id]
        if provider:
            settings = [s for s in settings if s.provider == provider]
        if config_type:
            settings = [s for s in settings if s.config_type == config_type]
        return settings

    async def delete(self, db, setting):
        self.items.pop((setting.model_id, setting.user_id), None)


class FakeSessionRepo:
    async def get_by_id(self, db, session_id):
        return None


@pytest.mark.asyncio
async def test_create_model_settings_encrypts_key_and_upserts(settings_factory, monkeypatch):
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt", lambda value: f"enc:{value}"
    )

    repo = FakeLLMRepo()
    service = ModelSettingService(
        repo=repo, config=settings_factory(), session_repo=FakeSessionRepo()
    )

    created = await service.create_model_settings(
        db=None,
        user_id="u1",
        model_setting_request=ModelSettingCreate(
            model_id="gpt-4o",
            provider="openai",
            api_key="plain-key",
        ),
    )

    assert created.has_api_key is True
    stored = repo.items[("gpt-4o", "u1")]
    assert stored.encrypted_api_key == "enc:plain-key"

    updated = await service.update_model_settings(
        db=None,
        setting_id=stored.id,
        user_id="u1",
        setting_update=ModelSettingUpdate(is_default=True),
    )

    assert updated.is_default is True


@pytest.mark.asyncio
async def test_delete_model_settings_returns_false_when_missing(settings_factory):
    service = ModelSettingService(
        repo=FakeLLMRepo(), config=settings_factory(), session_repo=FakeSessionRepo()
    )

    assert await service.delete_model_settings(None, model_id="missing", user_id="u1") is False
