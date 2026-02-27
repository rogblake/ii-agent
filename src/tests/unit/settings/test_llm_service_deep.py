"""Deep unit tests for LLMSettingService covering all branches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest

# Import all models before LLMSetting to satisfy SQLAlchemy mapper dependencies
import ii_agent.settings.mcp.models  # noqa: F401
import ii_agent.files.models  # noqa: F401
import ii_agent.sessions.wishlist.models  # noqa: F401
import ii_agent.integrations.connectors.models  # noqa: F401
import ii_agent.billing.models  # noqa: F401
import ii_agent.projects.models  # noqa: F401
import ii_agent.content.skills.models  # noqa: F401
import ii_agent.content.slides.models  # noqa: F401
import ii_agent.content.storybook.models  # noqa: F401
import ii_agent.projects.databases.models  # noqa: F401
import ii_agent.projects.subdomains.models  # noqa: F401
import ii_agent.projects.deployments.models  # noqa: F401

from ii_agent.core.config.llm_config import APITypes
from ii_agent.settings.llm.exceptions import LLMSettingNotFoundError
from ii_agent.settings.llm.schemas import (
    ModelSettingCreate,
    ModelSettingUpdate,
)
from ii_agent.settings.llm.service import LLMSettingService, get_system_llm_config

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


def _make_llm_setting(
    model: str = "gpt-4o",
    user_id: str = "user-1",
    setting_id: str | None = None,
    api_key: str = "enc:test-key",
    is_active: bool = True,
    api_type: str = "openai",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=setting_id or str(uuid.uuid4()),
        user_id=user_id,
        model=model,
        api_type=api_type,
        encrypted_api_key=api_key,
        base_url=None,
        max_retries=10,
        max_message_chars=30000,
        temperature=0.0,
        thinking_tokens=16000,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        llm_metadata=None,
    )


class FakeLLMRepo:
    def __init__(self, items: dict | None = None):
        # key = (model, user_id) or just id string
        self.items: dict = items or {}

    async def get_by_model_and_user(self, db, model, user_id):
        return self.items.get((model, user_id))

    async def get_by_id_and_user(self, db, setting_id, user_id):
        for s in self.items.values():
            if s.id == setting_id and s.user_id == user_id:
                return s
        return None

    async def list_by_user(self, db, user_id, api_type=None):
        result = [s for s in self.items.values() if s.user_id == user_id]
        if api_type:
            result = [s for s in result if s.api_type == api_type]
        return result

    async def create(self, db, setting):
        self.items[(setting.model, setting.user_id)] = setting
        return setting

    async def update(self, db, setting):
        # Update in-place; key may need refresh if model changed
        # Find by id
        for k, v in list(self.items.items()):
            if v is setting:
                self.items[k] = setting
                return setting
        # Fallback
        self.items[(setting.model, setting.user_id)] = setting
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
    config=None,
    settings_factory=None,
) -> LLMSettingService:
    if config is None and settings_factory is not None:
        config = settings_factory()
    elif config is None:
        # minimal config
        config = SimpleNamespace(llm_configs={})

    return LLMSettingService(
        repo=repo or FakeLLMRepo(),
        config=config,
        session_repo=session_repo or FakeSessionRepo(),
    )


# ---------------------------------------------------------------------------
# Tests – create_model_settings
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
        user_id="u1",
        setting_model_in=ModelSettingCreate(
            model="gpt-4o",
            api_type=APITypes.OPENAI,
            api_key="raw-key",
        ),
    )

    assert result.model == "gpt-4o"
    assert result.has_api_key is True
    stored = repo.items[("gpt-4o", "u1")]
    assert stored.encrypted_api_key == "enc:raw-key"


@pytest.mark.asyncio
async def test_create_model_settings_updates_existing(monkeypatch):
    """Given an existing setting for the same model, it is updated in-place."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    existing = _make_llm_setting(model="gpt-4o", user_id="u1")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): existing})
    svc = _make_service(repo=repo)

    result = await svc.create_model_settings(
        db=None,
        user_id="u1",
        setting_model_in=ModelSettingCreate(
            model="gpt-4o",
            api_type=APITypes.OPENAI,
            api_key="new-key",
            temperature=0.7,
        ),
    )

    assert result.temperature == 0.7
    assert existing.encrypted_api_key == "enc:new-key"


@pytest.mark.asyncio
async def test_create_model_settings_with_metadata(monkeypatch):
    """Metadata is stored on the new setting."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    repo = FakeLLMRepo()
    svc = _make_service(repo=repo)

    await svc.create_model_settings(
        db=None,
        user_id="u1",
        setting_model_in=ModelSettingCreate(
            model="claude-3-opus",
            api_type=APITypes.ANTHROPIC,
            api_key="key",
            metadata={"thinking": True},
        ),
    )

    stored = repo.items[("claude-3-opus", "u1")]
    assert stored.llm_metadata == {"thinking": True}


# ---------------------------------------------------------------------------
# Tests – update_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_model_settings_partial_update(monkeypatch):
    """Only provided fields are updated; others remain unchanged."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    setting_id = str(uuid.uuid4())
    existing = _make_llm_setting(model="gpt-4o", user_id="u1", setting_id=setting_id)
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): existing})
    svc = _make_service(repo=repo)

    result = await svc.update_model_settings(
        db=None,
        model_id=setting_id,
        user_id="u1",
        setting_update=ModelSettingUpdate(temperature=0.9),
    )

    assert result.temperature == 0.9
    # max_retries unchanged
    assert result.max_retries == 10


@pytest.mark.asyncio
async def test_update_model_settings_updates_api_key(monkeypatch):
    """When api_key is provided, it is encrypted and stored."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    setting_id = str(uuid.uuid4())
    existing = _make_llm_setting(setting_id=setting_id, user_id="u1")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): existing})
    svc = _make_service(repo=repo)

    await svc.update_model_settings(
        db=None,
        model_id=setting_id,
        user_id="u1",
        setting_update=ModelSettingUpdate(api_key="brand-new"),
    )

    assert existing.encrypted_api_key == "enc:brand-new"


@pytest.mark.asyncio
async def test_update_model_settings_not_found_raises():
    """Non-existent setting raises LLMSettingNotFoundError."""
    svc = _make_service()

    with pytest.raises(LLMSettingNotFoundError):
        await svc.update_model_settings(
            db=None,
            model_id="non-existent",
            user_id="u1",
            setting_update=ModelSettingUpdate(temperature=0.5),
        )


@pytest.mark.asyncio
async def test_update_model_settings_is_active_flag(monkeypatch):
    """is_active flag is applied when provided."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt",
        lambda v: f"enc:{v}",
    )
    setting_id = str(uuid.uuid4())
    existing = _make_llm_setting(setting_id=setting_id, user_id="u1", is_active=True)
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): existing})
    svc = _make_service(repo=repo)

    result = await svc.update_model_settings(
        db=None,
        model_id=setting_id,
        user_id="u1",
        setting_update=ModelSettingUpdate(is_active=False),
    )

    assert result.is_active is False


# ---------------------------------------------------------------------------
# Tests – get_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_settings_returns_info_without_key(monkeypatch):
    """Default get_model_settings does not include the API key."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id="u1")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_model_settings(db=None, model_id=setting_id, user_id="u1")

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
    setting = _make_llm_setting(setting_id=setting_id, user_id="u1")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_model_settings(
        db=None, model_id=setting_id, user_id="u1", include_key=True
    )

    assert result is not None
    assert result.api_key == "decrypted-key"


@pytest.mark.asyncio
async def test_get_model_settings_not_found_returns_none():
    """Non-existent setting returns None."""
    svc = _make_service()

    result = await svc.get_model_settings(db=None, model_id="missing", user_id="u1")

    assert result is None


# ---------------------------------------------------------------------------
# Tests – get_model_settings_by_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_model_settings_by_name_success(monkeypatch):
    """Returns setting when model name matches."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted",
    )
    setting = _make_llm_setting(model="my-model", user_id="u1")
    repo = FakeLLMRepo(items={("my-model", "u1"): setting})
    svc = _make_service(repo=repo)

    result = await svc.get_model_settings_by_name(
        db=None, model_name="my-model", user_id="u1"
    )

    assert result is not None
    assert result.model == "my-model"


@pytest.mark.asyncio
async def test_get_model_settings_by_name_not_found():
    """Returns None when no setting matches model name."""
    svc = _make_service()

    result = await svc.get_model_settings_by_name(
        db=None, model_name="non-existent", user_id="u1"
    )

    assert result is None


# ---------------------------------------------------------------------------
# Tests – list_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_model_settings_returns_all_for_user():
    """All settings for a user are returned."""
    settings = {
        ("gpt-4o", "u1"): _make_llm_setting(model="gpt-4o", user_id="u1"),
        ("claude-3", "u1"): _make_llm_setting(model="claude-3", user_id="u1", api_type="anthropic"),
        ("gpt-4o", "u2"): _make_llm_setting(model="gpt-4o", user_id="u2"),
    }
    repo = FakeLLMRepo(items=settings)
    svc = _make_service(repo=repo)

    result = await svc.list_model_settings(db=None, user_id="u1")

    assert len(result.models) == 2


@pytest.mark.asyncio
async def test_list_model_settings_filtered_by_api_type():
    """api_type filter is applied."""
    settings = {
        ("gpt-4o", "u1"): _make_llm_setting(model="gpt-4o", user_id="u1", api_type="openai"),
        ("claude-3", "u1"): _make_llm_setting(model="claude-3", user_id="u1", api_type="anthropic"),
    }
    repo = FakeLLMRepo(items=settings)
    svc = _make_service(repo=repo)

    result = await svc.list_model_settings(db=None, user_id="u1", api_type="openai")

    assert len(result.models) == 1
    assert result.models[0].model == "gpt-4o"


# ---------------------------------------------------------------------------
# Tests – delete_model_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_model_settings_success():
    """Existing setting is deleted; returns True."""
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id="u1")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): setting})
    svc = _make_service(repo=repo)

    result = await svc.delete_model_settings(db=None, model_id=setting_id, user_id="u1")

    assert result is True
    assert len(repo.items) == 0


@pytest.mark.asyncio
async def test_delete_model_settings_not_found_returns_false():
    """Non-existent setting returns False."""
    svc = _make_service()

    result = await svc.delete_model_settings(db=None, model_id="ghost", user_id="u1")

    assert result is False


# ---------------------------------------------------------------------------
# Tests – get_all_available_models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_available_models_combines_system_and_user(settings_factory):
    """System configs and user settings are merged into one list."""
    from ii_agent.core.config.llm_config import LLMConfig
    from pydantic import SecretStr

    sys_config = SimpleNamespace(
        model="gpt-4o",
        api_type=APITypes.OPENAI,
        api_key=SecretStr("key"),
    )
    config = settings_factory(llm_configs={"default": sys_config})

    setting = _make_llm_setting(model="claude-3", user_id="u1", api_type="anthropic")
    repo = FakeLLMRepo(items={("claude-3", "u1"): setting})
    svc = _make_service(repo=repo, config=config)

    result = await svc.get_all_available_models(db=None, user_id="u1")

    assert len(result.models) == 2
    sources = {m.source for m in result.models}
    assert "system" in sources
    assert "user" in sources


@pytest.mark.asyncio
async def test_get_all_available_models_no_system_configs():
    """No system configs returns only user settings."""
    config = SimpleNamespace(llm_configs={})
    setting = _make_llm_setting(model="custom", user_id="u1")
    repo = FakeLLMRepo(items={("custom", "u1"): setting})
    svc = _make_service(repo=repo, config=config)

    result = await svc.get_all_available_models(db=None, user_id="u1")

    assert len(result.models) == 1
    assert result.models[0].source == "user"


# ---------------------------------------------------------------------------
# Tests – get_user_llm_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_llm_config_success(monkeypatch):
    """Returns LLMConfig from user setting when found."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "decrypted-api-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id="u1", api_key="enc:key")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): setting})
    svc = _make_service(repo=repo)

    config = await svc.get_user_llm_config(db=None, model_id=setting_id, user_id="u1")

    assert config.model == "gpt-4o"


@pytest.mark.asyncio
async def test_get_user_llm_config_not_found_raises():
    """Raises ValueError when setting not found."""
    svc = _make_service()

    with pytest.raises(ValueError, match="LLM setting not found"):
        await svc.get_user_llm_config(db=None, model_id="missing", user_id="u1")


# ---------------------------------------------------------------------------
# Tests – get_llm_settings (session-based resolution)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_llm_settings_no_llm_setting_id_uses_system(settings_factory):
    """Session without llm_setting_id falls back to system config."""
    from ii_agent.core.config.llm_config import LLMConfig
    from pydantic import SecretStr

    sys_config = SimpleNamespace(
        model="gpt-4o",
        api_type=APITypes.OPENAI,
        api_key=SecretStr("sys-key"),
        setting_id=None,
        config_type=None,
    )
    config = settings_factory(llm_configs={"gpt-4o": sys_config})

    db_session = SimpleNamespace(llm_setting_id=None)
    session_repo = FakeSessionRepo(session=db_session)

    session_info = SimpleNamespace(id="sess-1", user_id="u1")
    svc = _make_service(session_repo=session_repo, config=config)

    llm_config = await svc.get_llm_settings(
        db=None, session=session_info, model_id="gpt-4o"
    )

    assert llm_config.model == "gpt-4o"


@pytest.mark.asyncio
async def test_get_llm_settings_no_llm_setting_id_user_source(monkeypatch):
    """source='user' forces user config lookup when no llm_setting_id on session."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "dec-key",
    )
    setting_id = str(uuid.uuid4())
    setting = _make_llm_setting(setting_id=setting_id, user_id="u1", model="gpt-4o")
    repo = FakeLLMRepo(items={("gpt-4o", "u1"): setting})

    db_session = SimpleNamespace(llm_setting_id=None)
    session_repo = FakeSessionRepo(session=db_session)
    session_info = SimpleNamespace(id="sess-1", user_id="u1")

    svc = _make_service(repo=repo, session_repo=session_repo)

    config = await svc.get_llm_settings(
        db=None, session=session_info, source="user", model_id=setting_id
    )

    assert config.model == "gpt-4o"


@pytest.mark.asyncio
async def test_get_llm_settings_with_llm_setting_id_falls_back_to_system(
    settings_factory, monkeypatch
):
    """When llm_setting_id exists but user config missing, system config is used."""
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.decrypt",
        lambda v: "key",
    )
    from pydantic import SecretStr

    llm_setting_id = "some-setting-id"
    sys_config = SimpleNamespace(
        model="gpt-4o",
        api_type=APITypes.OPENAI,
        api_key=SecretStr("sys"),
        setting_id=None,
        config_type=None,
    )
    config = settings_factory(llm_configs={llm_setting_id: sys_config})

    db_session = SimpleNamespace(llm_setting_id=llm_setting_id)
    session_repo = FakeSessionRepo(session=db_session)
    # No user settings for this id
    repo = FakeLLMRepo()

    session_info = SimpleNamespace(id="sess-1", user_id="u1")
    svc = _make_service(repo=repo, session_repo=session_repo, config=config)

    cfg = await svc.get_llm_settings(db=None, session=session_info)

    assert cfg.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Tests – get_system_llm_config (standalone helper)
# ---------------------------------------------------------------------------


def test_get_system_llm_config_success():
    """Returns config from system configs map."""
    from pydantic import SecretStr

    config = SimpleNamespace(
        llm_configs={
            "my-model": SimpleNamespace(
                model="gpt-4o",
                api_type=APITypes.OPENAI,
                api_key=SecretStr("key"),
                setting_id=None,
                config_type=None,
            )
        }
    )

    result = get_system_llm_config(model_id="my-model", config=config)

    assert result.model == "gpt-4o"
    assert result.setting_id == "my-model"
    assert result.config_type == "system"


def test_get_system_llm_config_not_found_raises():
    """Raises ValueError when model_id not in system configs."""
    config = SimpleNamespace(llm_configs={})

    with pytest.raises(ValueError, match="LLM config not found"):
        get_system_llm_config(model_id="missing", config=config)
