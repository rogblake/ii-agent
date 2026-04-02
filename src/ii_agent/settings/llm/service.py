"""Service layer for llm_settings domain - business logic only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.settings.llm.models import LLMSetting
from ii_agent.settings.llm.exceptions import LLMSettingNotFoundError
from ii_agent.settings.llm.repository import LLMSettingRepository
from ii_agent.settings.llm.schemas import (
    ModelSettingCreate,
    ModelSettingUpdate,
    ModelSettingInfo,
    ModelSettingInfoWithKey,
    ModelSettingList,
    LLMModelInfo,
    LLMModelList,
)
from ii_agent.sessions.repository import SessionRepository
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.utils.encryption import encryption_manager
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.settings import Settings


class LLMSettingService:
    """Service for managing LLM settings - business logic layer."""

    def __init__(
        self,
        *,
        repo: LLMSettingRepository,
        config: Settings,
        session_repo: SessionRepository,
    ) -> None:
        self._config = config
        self._repo = repo
        self._session_repo = session_repo

    async def create_model_settings(
        self, db: AsyncSession, *, setting_model_in: ModelSettingCreate, user_id: str
    ) -> ModelSettingInfo:
        """Create or update model settings for a specific model."""
        existing = await self._repo.get_by_model_and_user(
            db, setting_model_in.model, user_id
        )

        encrypted_api_key = encryption_manager.encrypt(setting_model_in.api_key)

        if existing:
            existing.api_type = setting_model_in.api_type.value
            existing.encrypted_api_key = encrypted_api_key
            existing.base_url = setting_model_in.base_url
            existing.max_retries = setting_model_in.max_retries
            existing.max_message_chars = setting_model_in.max_message_chars
            existing.temperature = setting_model_in.temperature
            existing.thinking_tokens = setting_model_in.thinking_tokens
            existing.llm_metadata = setting_model_in.metadata
            existing.updated_at = datetime.now(timezone.utc)

            updated = await self._repo.update(db, existing)
            return _to_model_setting_info(updated)
        else:
            new_setting = LLMSetting(
                id=str(uuid.uuid4()),
                user_id=user_id,
                model=setting_model_in.model,
                api_type=setting_model_in.api_type.value,
                encrypted_api_key=encrypted_api_key,
                base_url=setting_model_in.base_url,
                max_retries=setting_model_in.max_retries,
                max_message_chars=setting_model_in.max_message_chars,
                temperature=setting_model_in.temperature,
                thinking_tokens=setting_model_in.thinking_tokens,
                llm_metadata=setting_model_in.metadata,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            created = await self._repo.create(db, new_setting)
            return _to_model_setting_info(created)

    async def update_model_settings(
        self,
        db: AsyncSession,
        *,
        model_id: str,
        setting_update: ModelSettingUpdate,
        user_id: str,
    ) -> ModelSettingInfo:
        """Update existing model settings.

        Raises:
            LLMSettingNotFoundError: If setting not found or access denied.
        """
        setting = await self._repo.get_by_id_and_user(db, model_id, user_id)
        if not setting:
            raise LLMSettingNotFoundError(
                f"Model setting {model_id} not found or access denied"
            )

        if setting_update.api_key is not None:
            setting.encrypted_api_key = encryption_manager.encrypt(setting_update.api_key)
        if setting_update.base_url is not None:
            setting.base_url = setting_update.base_url
        if setting_update.max_retries is not None:
            setting.max_retries = setting_update.max_retries
        if setting_update.max_message_chars is not None:
            setting.max_message_chars = setting_update.max_message_chars
        if setting_update.temperature is not None:
            setting.temperature = setting_update.temperature
        if setting_update.thinking_tokens is not None:
            setting.thinking_tokens = setting_update.thinking_tokens
        if setting_update.metadata is not None:
            setting.llm_metadata = setting_update.metadata
        if setting_update.is_active is not None:
            setting.is_active = setting_update.is_active

        setting.updated_at = datetime.now(timezone.utc)
        updated = await self._repo.update(db, setting)
        return _to_model_setting_info(updated)

    async def get_model_settings(
        self,
        db: AsyncSession,
        *,
        model_id: str,
        user_id: str,
        include_key: bool = False,
    ) -> Optional[ModelSettingInfoWithKey | ModelSettingInfo]:
        """Get model settings by ID."""
        setting = await self._repo.get_by_id_and_user(db, model_id, user_id)
        if not setting:
            return None

        return _to_model_setting_info(setting, include_key=include_key)

    async def get_model_settings_by_name(
        self,
        db: AsyncSession,
        *,
        model_name: str,
        user_id: str,
        include_key: bool = False,
    ) -> Optional[ModelSettingInfoWithKey | ModelSettingInfo]:
        """Get model settings by model name."""
        setting = await self._repo.get_by_model_and_user(db, model_name, user_id)
        if not setting:
            return None

        return _to_model_setting_info(setting, include_key=include_key)

    async def list_model_settings(
        self, db: AsyncSession, *, user_id: str, api_type: Optional[str] = None
    ) -> ModelSettingList:
        """List all model settings for a user."""
        settings = await self._repo.list_by_user(db, user_id, api_type=api_type)
        model_list = [_to_model_setting_info(s) for s in settings]
        return ModelSettingList(models=model_list)

    async def delete_model_settings(
        self, db: AsyncSession, *, model_id: str, user_id: str
    ) -> bool:
        """Delete model settings by ID."""
        setting = await self._repo.get_by_id_and_user(db, model_id, user_id)
        if not setting:
            return False

        await self._repo.delete(db, setting)
        return True

    async def get_all_available_models(
        self, db: AsyncSession, *, user_id: str
    ) -> LLMModelList:
        """Get all available models from both system configs and user settings."""
        models = []

        for model_id, llm_config in self._config.llm_configs.items():
            models.append(
                LLMModelInfo(
                    id=model_id,
                    model=llm_config.model,
                    api_type=llm_config.api_type,
                    source="system",
                    description=f"System configured {model_id}",
                )
            )

        user_settings = await self.list_model_settings(db, user_id=user_id)

        for setting in user_settings.models:
            models.append(
                LLMModelInfo(
                    id=setting.id,
                    model=setting.model,
                    api_type=setting.api_type,
                    source="user",
                    description=f"User configured {setting.model}",
                )
            )

        return LLMModelList(models=models)

    async def get_user_llm_config(
        self, db: AsyncSession, *, model_id: str, user_id: str
    ) -> LLMConfig:
        """Get LLM config from user settings in database.

        Raises:
            ValueError: If config not found.
        """
        llm_setting = await self.get_model_settings(
            db,
            model_id=model_id,
            user_id=user_id,
            include_key=True,
        )

        if not llm_setting:
            raise ValueError(f"LLM setting not found for model_id: {model_id}")

        return llm_setting.to_llm_config()

    async def get_llm_settings(
        self,
        db: AsyncSession,
        *,
        session: SessionInfo,
        source: str | None = None,
        model_id: str | None = None,
    ) -> LLMConfig:
        """Get LLM settings based on the session's llm_setting_id.

        Looks up the session in the database to retrieve its ``llm_setting_id``
        and resolves to either a user or system LLM config.

        Args:
            db: Database session.
            session: Session info (used to look up the session record).
            source: "user" to prefer user configs, otherwise system configs.
            model_id: The model ID requested by the caller.
        """
        current_session = await self._session_repo.get_by_id(db, session.id)
        llm_setting_id = current_session.llm_setting_id if current_session else None

        if llm_setting_id is None:
            if source == "user":
                return await self.get_user_llm_config(
                    db,
                    model_id=model_id,
                    user_id=str(session.user_id),
                )
            else:
                return get_system_llm_config(model_id=model_id, config=self._config)
        else:
            try:
                return await self.get_user_llm_config(
                    db,
                    model_id=llm_setting_id,
                    user_id=str(session.user_id),
                )
            except ValueError:
                return get_system_llm_config(
                    model_id=llm_setting_id,
                    config=self._config,
                )


# ---------------------------------------------------------------------------
# Standalone helpers (no db access needed)
# ---------------------------------------------------------------------------


def get_system_llm_config(*, model_id: str, config: Settings) -> LLMConfig:
    """Get LLM config from system configuration.

    Raises:
        ValueError: If config not found.
    """
    llm_config = config.llm_configs.get(model_id)
    if not llm_config:
        raise ValueError(f"LLM config not found for model: {model_id}")
    llm_config.setting_id = model_id
    llm_config.config_type = "system"
    return llm_config


# ---------------------------------------------------------------------------
# Private converter helpers
# ---------------------------------------------------------------------------


def _to_model_setting_info(
    setting: LLMSetting, *, include_key: bool = False
) -> ModelSettingInfoWithKey | ModelSettingInfo:
    """Convert database model to Pydantic model.

    When *include_key* is ``True`` the returned object is a
    ``ModelSettingInfoWithKey`` containing the decrypted API key.
    """
    shared = dict(
        id=setting.id,
        model=setting.model,
        api_type=setting.api_type,
        base_url=setting.base_url,
        max_retries=setting.max_retries,
        max_message_chars=setting.max_message_chars,
        temperature=setting.temperature,
        thinking_tokens=setting.thinking_tokens,
        is_active=setting.is_active,
        has_api_key=bool(setting.encrypted_api_key),
        created_at=setting.created_at.isoformat() if setting.created_at else "",
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
        metadata=setting.llm_metadata or {},
    )

    if include_key:
        return ModelSettingInfoWithKey(
            **shared,
            api_key=(
                encryption_manager.decrypt(setting.encrypted_api_key)
                if setting.encrypted_api_key
                else None
            ),
        )

    return ModelSettingInfo(**shared)
