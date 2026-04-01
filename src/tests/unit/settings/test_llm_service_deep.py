"""Deep unit tests for LLMSettingService covering all branches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

# Import all models before LLMSetting to satisfy SQLAlchemy mapper dependencies
import ii_agent.settings.mcp.models  # noqa: F401
import ii_agent.files.models  # noqa: F401
import ii_agent.sessions.wishlist.models  # noqa: F401
import ii_agent.integrations.connectors.models  # noqa: F401
import ii_agent.billing.models  # noqa: F401
import ii_agent.projects.models  # noqa: F401
import ii_agent.settings.skills.models  # noqa: F401
import ii_agent.content.slides.models  # noqa: F401
import ii_agent.content.storybook.models  # noqa: F401
import ii_agent.projects.databases.models  # noqa: F401
import ii_agent.projects.subdomains.models  # noqa: F401
import ii_agent.projects.deployments.models  # noqa: F401

from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.exceptions import LLMSettingNotFoundError
from ii_agent.settings.llm.schemas import (
    ModelParams,
    ModelSettingCreate,
    ModelSettingUpdate,
)
from ii_agent.settings.llm.service import ModelSettingService, get_system_llm_config_from_db

pytestmark = pytest.mark.unit

# Stable test UUIDs
U1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
U2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
SESS_1 = uuid.UUID("00000000-0000-0000-0000-000000000011")


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


_UNSET = object()


def _make_llm_setting(
    model_id: str = "gpt-4o",
    user_id: uuid.UUID | str | None = _UNSET,
    setting_id: str | None = None,
    api_key: str = "enc:test-key",
    is_default: bool = True,
    provider: str = "openai",
) -> SimpleNamespace:
    if user_id is _UNSET:
        user_id = U1
    return SimpleNamespace(
        id=setting_id or str(uuid.uuid4()),
        user_id=user_id,
        model_id=model_id,
        provider=provider,
        encrypted_api_key=api_key,
        base_url=None,
        display_name=None,
        configs={
            "max_retries": 10,
            "max_message_chars": 30000,
            "temperature": 0.0,
            "thinking_tokens": 16000,
        },
        pricing=None,
        config_type="user",
        is_default=is_default,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class FakeLLMRepo:
    def __init__(self, items: dict | None = None):
        # key = (model_id, user_id) or just id string
        self.items: dict = items or {}

    async def get_by_model_and_user(self, db, model_id, user_id):
        return self.items.get((model_id, user_id))

    async def get_by_id_and_user(self, db, setting_id, user_id):
        for s in self.items.values():
            if str(s.id) == str(setting_id) and str(s.user_id) == str(user_id):
                return s
        return None

    async def list_by_user(self, db, user_id, provider=None, config_type=None):
        result = [s for s in self.items.values() if s.user_id == user_id]
        if provider:
            result = [s for s in result if s.provider == provider]
        if config_type:
            result = [s for s in result if s.config_type == config_type]
        return result

    async def create(self, db, setting):
        if setting.id is None:
            setting.id = uuid.uuid4()
        if not hasattr(setting, "created_at") or setting.created_at is None:
            setting.created_at = datetime.now(timezone.utc)
        if not hasattr(setting, "updated_at") or setting.updated_at is None:
            setting.updated_at = datetime.now(timezone.utc)
        self.items[(setting.model_id, setting.user_id)] = setting
        return setting

    async def update(self, db, setting):
        # Update in-place; key may need refresh if model changed
        # Find by id
        for k, v in list(self.items.items()):
            if v is setting:
                self.items[k] = setting
                return setting
        # Fallback
        self.items[(setting.model_id, setting.user_id)] = setting
        return setting

    async def delete(self, db, setting):
        for k, v in list(self.items.items()):
            if v is setting:
                del self.items[k]
                return


class FakeSessionRepo:
    def __init__(self, session=None):
        self._session = session

    async def get_by_id(self, db, session_id):
        return self._session


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _make_service(
    repo: FakeLLMRepo | None = None,
    session_repo: FakeSessionRepo | None = None,
) -> ModelSettingService:
    return ModelSettingService(
        repo=repo or FakeLLMRepo(),
        session_repo=session_repo or FakeSessionRepo(),
    )


# ---------------------------------------------------------------------------
# Tests -- create_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_model_settings_new_record(monkeypatch):
    """Given no existing setting, a new one is created and encrypted."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    repo = FakeLLMRepo()
    svc = _make_service(repo=repo)

    result = await svc.create_model_settings(
        db=None,
        user_id=U1,
        model_setting_request=ModelSettingCreate(
            model_id="gpt-4o",
            provider="openai",
            api_key="raw-key",
        ),
    )

    assert result.model_id == "gpt-4o"
    assert result.has_api_key is True
    stored = repo.items[("gpt-4o", U1)]
    assert stored.encrypted_api_key == "enc:raw-key"


@pytest.mark.asyncio
async def test_create_model_settings_updates_existing(monkeypatch):
    """Given an existing setting for the same model, it is updated in-place."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    existing = _make_llm_setting(model_id="gpt-4o", user_id=U1)
    repo = FakeLLMRepo(items={("gpt-4o", U1): existing})
    svc = _make_service(repo=repo)

    result = await svc.create_model_settings(
        db=None,
        user_id=U1,
        model_setting_request=ModelSettingCreate(
            model_id="gpt-4o",
            provider="openai",
            api_key="new-key",
            configs=ModelParams(temperature=0.7),
        ),
    )

    assert result.configs.temperature == 0.7
    assert existing.encrypted_api_key == "enc:new-key"


@pytest.mark.asyncio
async def test_create_model_settings_with_configs(monkeypatch):
    """Configs JSONB is stored on the new setting."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    repo = FakeLLMRepo()
    svc = _make_service(repo=repo)

    await svc.create_model_settings(
        db=None,
        user_id=U1,
        model_setting_request=ModelSettingCreate(
            model_id="claude-3-opus",
            provider="anthropic",
            api_key="key",
            configs=ModelParams(thinking_tokens=32000, cot_model=True),
        ),
    )

    stored = repo.items[("claude-3-opus", U1)]
    assert stored.configs["thinking_tokens"] == 32000
    assert stored.configs["cot_model"] is True


# ---------------------------------------------------------------------------
# Tests -- update_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_model_settings_partial_update(monkeypatch):
    """Only provided fields are updated; others remain unchanged."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    setting_id = str(uuid.uuid4())
    existing = _make_llm_setting(model_id="gpt-4o", user_id=U1, setting_id=setting_id)
    repo = FakeLLMRepo(items={("gpt-4o", U1): existing})
    svc = _make_service(repo=repo)

    result = await svc.update_model_settings(
        db=None,
        setting_id=setting_id,
        user_id=U1,
        setting_update=ModelSettingUpdate(configs=ModelParams(temperature=0.9)),
    )

    assert result.configs.temperature == 0.9


@pytest.mark.asyncio
async def test_update_model_settings_updates_api_key(monkeypatch):
    """When api_key is provided, it is encrypted and stored."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    setting_id = str(uuid.uuid4())
    existing = _make_llm_setting(setting_id=setting_id, user_id=U1)
    repo = FakeLLMRepo(items={("gpt-4o", U1): existing})
    svc = _make_service(repo=repo)

    await svc.update_model_settings(
        db=None,
        setting_id=setting_id,
        user_id=U1,
        setting_update=ModelSettingUpdate(api_key="brand-new"),
    )

    assert existing.encrypted_api_key == "enc:brand-new"


@pytest.mark.asyncio
async def test_update_model_settings_not_found_raises():
    """Non-existent setting raises LLMSettingNotFoundError."""
    svc = _make_service()
    missing_id = uuid.uuid4()

    with pytest.raises(LLMSettingNotFoundError):
        await svc.update_model_settings(
            db=None,
            setting_id=missing_id,
            user_id=U1,
            setting_update=ModelSettingUpdate(configs=ModelParams(temperature=0.5)),
        )


@pytest.mark.asyncio
async def test_update_model_settings_is_default_flag(monkeypatch):
    """is_default flag is applied when provided."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    setting_id = str(uuid.uuid4())
    existing = _make_llm_setting(setting_id=setting_id, user_id=U1, is_default=True)
    repo = FakeLLMRepo(items={("gpt-4o", U1): existing})
    svc = _make_service(repo=repo)

    result = await svc.update_model_settings(
        db=None,
        setting_id=setting_id,
        user_id=U1,
        setting_update=ModelSettingUpdate(is_default=False),
    )

    assert result.is_default is False


# ---------------------------------------------------------------------------
# Tests -- get_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_settings_returns_info_without_key(monkeypatch):
    """Default get_model_settings does not include the API key."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id=U1)
    repo = FakeLLMRepo(items={("gpt-4o", U1): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_model_settings(db=None, setting_id=setting_id, user_id=U1)

    assert result is not None
    assert not hasattr(result, "api_key") or result.api_key is None


@pytest.mark.asyncio
async def test_get_model_settings_with_key(monkeypatch):
    """include_key=True returns ModelSettingInfoWithKey with decrypted key."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id=U1)
    repo = FakeLLMRepo(items={("gpt-4o", U1): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_model_settings(
        db=None, setting_id=setting_id, user_id=U1, include_key=True
    )

    assert result is not None
    assert result.api_key == "decrypted-key"


@pytest.mark.asyncio
async def test_get_model_settings_not_found_returns_none():
    """Non-existent setting returns None."""
    svc = _make_service()

    result = await svc.get_model_settings(db=None, setting_id=uuid.uuid4(), user_id=U1)

    assert result is None


# ---------------------------------------------------------------------------
# Tests -- get_model_settings_by_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_settings_by_name_success(monkeypatch):
    """Returns setting when model name matches."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted",
    )
    setting = _make_llm_setting(model_id="my-model", user_id=U1)
    repo = FakeLLMRepo(items={("my-model", U1): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_model_settings_by_name(db=None, model_name="my-model", user_id=U1)

    assert result is not None
    assert result.model_id == "my-model"


@pytest.mark.asyncio
async def test_get_model_settings_by_name_not_found():
    """Returns None when no setting matches model name."""
    svc = _make_service()

    result = await svc.get_model_settings_by_name(db=None, model_name="non-existent", user_id=U1)

    assert result is None


# ---------------------------------------------------------------------------
# Tests -- list_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_model_settings_returns_all_for_user():
    """All settings for a user are returned."""
    settings = {
        ("gpt-4o", U1): _make_llm_setting(model_id="gpt-4o", user_id=U1),
        ("claude-3", U1): _make_llm_setting(model_id="claude-3", user_id=U1, provider="anthropic"),
        ("gpt-4o", U2): _make_llm_setting(model_id="gpt-4o", user_id=U2),
    }
    repo = FakeLLMRepo(items=settings)
    svc = _make_service(repo=repo)

    result = await svc.list_model_settings(db=None, user_id=U1)

    assert len(result.models) == 2


@pytest.mark.asyncio
async def test_list_model_settings_filtered_by_provider():
    """provider filter is applied."""
    settings = {
        ("gpt-4o", U1): _make_llm_setting(model_id="gpt-4o", user_id=U1, provider="openai"),
        ("claude-3", U1): _make_llm_setting(model_id="claude-3", user_id=U1, provider="anthropic"),
    }
    repo = FakeLLMRepo(items=settings)
    svc = _make_service(repo=repo)

    result = await svc.list_model_settings(db=None, user_id=U1, provider="openai")

    assert len(result.models) == 1
    assert result.models[0].model_id == "gpt-4o"


# ---------------------------------------------------------------------------
# Tests -- delete_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_model_settings_success():
    """Existing setting is deleted; returns True."""
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id=U1)
    repo = FakeLLMRepo(items={("gpt-4o", U1): setting})
    svc = _make_service(repo=repo)

    result = await svc.delete_model_settings(db=None, model_id=setting_id, user_id=U1)

    assert result is True
    assert len(repo.items) == 0


@pytest.mark.asyncio
async def test_delete_model_settings_not_found_returns_false():
    """Non-existent setting returns False."""
    svc = _make_service()

    result = await svc.delete_model_settings(db=None, model_id=uuid.uuid4(), user_id=U1)

    assert result is False


# ---------------------------------------------------------------------------
# Tests -- get_all_available_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_available_models_combines_system_and_user():
    """System configs (from DB) and user settings are merged into one list."""
    system_setting = _make_llm_setting(
        model_id="gpt-4o",
        user_id=None,
        provider="openai",
    )
    system_setting.config_type = "system"
    system_setting.user_id = None

    user_setting = _make_llm_setting(model_id="claude-3", user_id=U1, provider="anthropic")

    class FakeLLMRepoWithSystem(FakeLLMRepo):
        async def list_system(self, db):
            return [system_setting]

    repo = FakeLLMRepoWithSystem(items={("claude-3", U1): user_setting})
    svc = _make_service(repo=repo)

    result = await svc.get_all_available_models(db=None, user_id=U1)

    assert len(result.models) == 2
    sources = {m.source for m in result.models}
    assert "system" in sources
    assert "user" in sources


@pytest.mark.asyncio
async def test_get_all_available_models_no_system_configs():
    """No system configs returns only user settings."""

    class FakeLLMRepoNoSystem(FakeLLMRepo):
        async def list_system(self, db):
            return []

    setting = _make_llm_setting(model_id="custom", user_id=U1)
    repo = FakeLLMRepoNoSystem(items={("custom", U1): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_all_available_models(db=None, user_id=U1)

    assert len(result.models) == 1
    assert result.models[0].source == "user"


# ---------------------------------------------------------------------------
# Tests -- get_user_llm_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_llm_config_success(monkeypatch):
    """Returns LLMConfig from user setting when found."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted-api-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id=U1, api_key="enc:key")
    repo = FakeLLMRepo(items={("gpt-4o", U1): setting})
    svc = _make_service(repo=repo)

    config = await svc.get_user_llm_config(db=None, setting_id=setting_id, user_id=U1)

    assert config.model == "gpt-4o"


@pytest.mark.asyncio
async def test_get_user_llm_config_not_found_raises():
    """Raises ValueError when setting not found."""
    svc = _make_service()

    with pytest.raises(ValueError, match="LLM setting not found"):
        await svc.get_user_llm_config(db=None, setting_id=uuid.uuid4(), user_id=U1)


# ---------------------------------------------------------------------------
# Tests -- get_llm_settings (session-based resolution)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_llm_settings_no_llm_setting_id_uses_system():
    """Session without llm_setting_id falls back to system config via DB."""
    db_session = SimpleNamespace(llm_setting_id=None)
    session_repo = FakeSessionRepo(session=db_session)

    session_info = SimpleNamespace(id=SESS_1, user_id=U1)
    svc = _make_service(session_repo=session_repo)

    # Mock resolve_system_config to return a system config
    from unittest.mock import AsyncMock

    svc.resolve_system_config = AsyncMock(
        return_value=SimpleNamespace(
            model="gpt-4o",
            provider=Provider.OPENAI,
            setting_id="gpt-4o",
            config_type="system",
        )
    )

    llm_config = await svc.get_llm_settings(db=None, session=session_info, model_id="gpt-4o")

    assert llm_config.model == "gpt-4o"


@pytest.mark.asyncio
async def test_get_llm_settings_no_llm_setting_id_user_source(monkeypatch):
    """source='user' forces user config lookup when no llm_setting_id on session."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "dec-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id=U1, model_id="gpt-4o")
    repo = FakeLLMRepo(items={("gpt-4o", U1): setting})

    db_session = SimpleNamespace(llm_setting_id=None)
    session_repo = FakeSessionRepo(session=db_session)
    session_info = SimpleNamespace(id=SESS_1, user_id=U1)

    svc = _make_service(repo=repo, session_repo=session_repo)

    config = await svc.get_llm_settings(
        db=None, session=session_info, source="user", model_id=setting_id
    )

    assert config.model == "gpt-4o"


@pytest.mark.asyncio
async def test_get_llm_settings_with_llm_setting_id_falls_back_to_system(monkeypatch):
    """When llm_setting_id exists but user config missing, system config is used via DB."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "key",
    )
    from unittest.mock import AsyncMock

    llm_setting_id = "some-setting-id"

    db_session = SimpleNamespace(llm_setting_id=llm_setting_id)
    session_repo = FakeSessionRepo(session=db_session)
    # No user settings for this id
    repo = FakeLLMRepo()

    session_info = SimpleNamespace(id=SESS_1, user_id=U1)
    svc = _make_service(repo=repo, session_repo=session_repo)

    # Mock resolve_config_by_setting_id to simulate DB-based fallback
    svc.resolve_config_by_setting_id = AsyncMock(
        return_value=SimpleNamespace(
            model="gpt-4o",
            provider=Provider.OPENAI,
            setting_id=llm_setting_id,
            config_type="system",
        )
    )

    cfg = await svc.get_llm_settings(db=None, session=session_info)

    assert cfg.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Tests -- get_system_llm_config_from_db (standalone async helper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_system_llm_config_from_db_success(monkeypatch):
    """Returns config from DB system settings."""
    from unittest.mock import AsyncMock

    fake_setting = _make_llm_setting(model_id="gpt-4o", user_id=None, provider="openai")
    fake_setting.user_id = None
    fake_setting.config_type = "system"
    fake_setting.is_active = True

    monkeypatch.setattr(
        "ii_agent.settings.llm.service.LLMSettingRepository.get_system_by_model",
        AsyncMock(return_value=fake_setting),
    )

    result = await get_system_llm_config_from_db(db=None, model_id="gpt-4o")

    assert result.model == "gpt-4o"
    assert result.config_type == "system"


@pytest.mark.asyncio
async def test_get_system_llm_config_from_db_not_found_raises(monkeypatch):
    """Raises ValueError when model_id not found in DB system settings."""
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "ii_agent.settings.llm.service.LLMSettingRepository.get_system_by_model",
        AsyncMock(return_value=None),
    )

    with pytest.raises(ValueError, match="System LLM config not found"):
        await get_system_llm_config_from_db(db=None, model_id="missing")
