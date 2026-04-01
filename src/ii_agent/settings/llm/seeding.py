"""System LLM settings seeding logic.

Seeds system-level LLM settings (user_id=NULL, config_type='system')
from the LLM_CONFIGS environment variable.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger


_seeding_done = False


async def seed_admin_llm_settings() -> None:
    """Seed system-level LLM settings from LLM_CONFIGS env var.

    System settings have ``user_id=NULL`` and ``config_type='system'``.
    They are keyed by the JSON object key which is stored as the row ``id``.
    """
    from ii_agent.settings.llm.models import ModelSetting
    from ii_agent.core.db import get_db_session_local

    llm_configs_str = get_settings().llm_configs_json
    if not llm_configs_str:
        logger.info(
            "LLM_CONFIGS environment variable not set, skipping system LLM settings seeding"
        )
        return

    try:
        llm_configs = json.loads(llm_configs_str)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing LLM_CONFIGS: {e}")
        return

    async with get_db_session_local() as db_session:
        try:
            # Fetch existing system settings (user_id IS NULL)
            existing_settings_result = await db_session.execute(
                select(ModelSetting).where(
                    ModelSetting.user_id.is_(None),
                    ModelSetting.config_type == "system",
                )
            )
            existing_settings = existing_settings_result.scalars().all()

            existing_settings_dict = {
                (setting.model_id, setting.provider): setting for setting in existing_settings
            }
            logger.info(f"Found {len(existing_settings_dict)} existing system LLM settings")

            added_count = 0
            updated_count = 0
            for model_id, config_data in llm_configs.items():
                encrypted_api_key = "empty"
                if config_data.get("api_key"):
                    from ii_agent.core.secrets.encryption import encryption_manager

                    encrypted_api_key = encryption_manager.encrypt(config_data["api_key"])

                # Build configs JSONB from flat config_data
                configs = {
                    "max_retries": config_data.get("max_retries", 10),
                    "max_message_chars": config_data.get("max_message_chars", 30000),
                    "temperature": config_data.get("temperature", 0.0),
                    "thinking_tokens": config_data.get("thinking_tokens", 16000),
                    "vertex_region": config_data.get("vertex_region"),
                    "vertex_project_id": config_data.get("vertex_project_id"),
                    "azure_endpoint": config_data.get("azure_endpoint"),
                    "azure_api_version": config_data.get("azure_api_version"),
                    "cot_model": config_data.get("cot_model", False),
                }

                # Map api_type to provider display name
                provider = _api_type_to_provider(config_data.get("api_type", "custom"))

                if model_id in existing_settings_dict:
                    existing_setting = existing_settings_dict[model_id]
                    existing_setting.model_id = config_data["model"]
                    existing_setting.provider = provider
                    existing_setting.encrypted_api_key = encrypted_api_key
                    existing_setting.base_url = config_data.get("base_url")
                    existing_setting.display_name = config_data.get("display_name")
                    existing_setting.params = configs
                    existing_setting.config_type = "system"
                    existing_setting.is_default = config_data.get("is_default", False)
                    existing_setting.updated_at = datetime.now(timezone.utc)
                    updated_count += 1
                    logger.info(
                        f"Updated system LLM setting: {config_data['model']} (ID: {existing_setting.id})"
                    )
                else:
                    llm_setting = ModelSetting(
                        model_id=config_data["model"],
                        user_id=None,
                        provider=provider,
                        encrypted_api_key=encrypted_api_key,
                        base_url=config_data.get("base_url"),
                        display_name=config_data.get("display_name"),
                        configs=configs,
                        config_type="system",
                        is_default=config_data.get("is_default", False),
                    )

                    db_session.add(llm_setting)
                    added_count += 1
                    logger.info(
                        f"Created system LLM setting: {config_data['model']} (ID: {llm_setting.id})"
                    )

            if added_count > 0 or updated_count > 0:
                logger.info(
                    f"Added {added_count} new and updated {updated_count} existing system LLM settings"
                )
            else:
                logger.info("No system LLM settings changes needed")

            await db_session.commit()
            logger.info("Successfully seeded system LLM settings")
        except Exception:
            raise


async def ensure_admin_llm_settings_seeded() -> None:
    """Ensure system LLM settings are seeded (run once)."""
    global _seeding_done
    if not _seeding_done:
        try:
            await seed_admin_llm_settings()
            _seeding_done = True
        except Exception as e:
            logger.error(f"Error seeding system LLM settings: {e}")


def _api_type_to_provider(api_type: str) -> str:
    """Map legacy api_type strings to Provider display names."""
    mapping = {
        "anthropic": "Anthropic",
        "openai": "OpenAI",
        "gemini": "Google",
        "custom": "Custom",
    }
    return mapping.get(api_type.lower(), "Custom")
