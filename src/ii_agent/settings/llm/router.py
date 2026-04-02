"""API routes for llm_settings domain."""

import uuid

from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.settings.llm.dependencies import ModelSettingServiceDep
from ii_agent.settings.llm.exceptions import LLMSettingNotFoundError
from ii_agent.settings.llm.schemas import (
    LLMModelList,
    ModelSettingCreate,
    ModelSettingInfo,
    ModelSettingUpdate,
)


router = APIRouter(prefix="/models", tags=["User LLM Settings Management"])


@router.post("", response_model=ModelSettingInfo)
async def create_model_setting(
    setting: ModelSettingCreate,
    current_user: CurrentUser,
    service: ModelSettingServiceDep,
    db: DBSession,
) -> ModelSettingInfo:
    """Create or update model settings for a specific model."""
    return await service.create_model_settings(
        db,
        model_setting_request=setting,
        user_id=current_user.id,
    )


@router.get("", response_model=LLMModelList)
async def list_available_models(
    current_user: CurrentUser,
    service: ModelSettingServiceDep,
    db: DBSession,
) -> LLMModelList:
    """List all available models for the current user."""
    return await service.get_all_available_models(
        db,
        user_id=current_user.id,
    )


@router.get("/{setting_id}", response_model=ModelSettingInfo)
async def get_model_setting(
    setting_id: uuid.UUID,
    current_user: CurrentUser,
    service: ModelSettingServiceDep,
    db: DBSession,
) -> ModelSettingInfo:
    """Get specific model settings by ID (includes API key)."""
    model_setting = await service.get_model_settings(
        db,
        setting_id=setting_id,
        user_id=current_user.id,
        include_key=True,
    )

    if not model_setting:
        raise LLMSettingNotFoundError("Model settings not found")

    return model_setting


@router.put("/{model_id}", response_model=ModelSettingInfo)
async def update_model_setting(
    model_id: uuid.UUID,
    setting_update: ModelSettingUpdate,
    current_user: CurrentUser,
    service: ModelSettingServiceDep,
    db: DBSession,
) -> ModelSettingInfo:
    """Update existing model settings."""
    return await service.update_model_settings(
        db,
        setting_id=model_id,
        setting_update=setting_update,
        user_id=current_user.id,
    )


@router.delete("/{model_id}")
async def delete_model_setting(
    model_id: uuid.UUID,
    current_user: CurrentUser,
    service: ModelSettingServiceDep,
    db: DBSession,
) -> dict[str, str]:
    """Delete model settings by ID."""
    deleted = await service.delete_model_settings(
        db,
        model_id=model_id,
        user_id=current_user.id,
    )

    if not deleted:
        raise LLMSettingNotFoundError("Model settings not found")

    return {"message": "Model settings deleted successfully"}
