"""Admin LLM settings seeding logic.

Extracted from core/db/manager.py to keep infrastructure code
free of domain-specific business logic.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger


_seeding_done = False


async def seed_admin_llm_settings():
    """Seed LLM settings for admin user with system models from LLM_CONFIGS."""
    from ii_agent.auth.users.models import User
    from ii_agent.settings.llm.models import LLMSetting
    from ii_agent.core.db.manager import get_db_session_local

    llm_configs_str = get_settings().llm_configs_json
    if not llm_configs_str:
        logger.info(
            "LLM_CONFIGS environment variable not set, skipping admin LLM settings seeding"
        )
        return

    try:
        llm_configs = json.loads(llm_configs_str)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing LLM_CONFIGS: {e}")
        return

    async with get_db_session_local() as db_session:
        try:
            admin_user = (
                await db_session.execute(
                    select(User).filter(User.email == "admin@ii.inc")
                )
            ).scalar_one_or_none()

            if not admin_user:
                admin_user = User(
                    id="admin",
                    email="admin@ii.inc",
                    first_name="Admin",
                    last_name="User",
                    role="admin",
                    is_active=True,
                    email_verified=True,
                    credits=1000.0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db_session.add(admin_user)
                await db_session.flush()
                logger.info("Created admin user with ID 'admin'")
            else:
                logger.info(f"Admin user already exists with ID: {admin_user.id}")

            existing_settings_result = await db_session.execute(
                select(LLMSetting).where(LLMSetting.user_id == admin_user.id)
            )
            existing_settings = existing_settings_result.scalars().all()

            existing_settings_dict = {
                setting.id: setting for setting in existing_settings
            }
            logger.info(
                f"Found {len(existing_settings_dict)} existing admin LLM settings"
            )

            added_count = 0
            updated_count = 0
            for model_id, config_data in llm_configs.items():
                encrypted_api_key = "empty"
                if config_data.get("api_key"):
                    from ii_agent.core.secrets.encryption import encryption_manager

                    encrypted_api_key = encryption_manager.encrypt(
                        config_data["api_key"]
                    )

                if model_id in existing_settings_dict:
                    existing_setting = existing_settings_dict[model_id]
                    existing_setting.model = config_data["model"]
                    existing_setting.api_type = config_data["api_type"]
                    existing_setting.encrypted_api_key = encrypted_api_key
                    existing_setting.base_url = config_data.get("base_url")
                    existing_setting.max_retries = config_data.get("max_retries", 10)
                    existing_setting.max_message_chars = config_data.get(
                        "max_message_chars", 30000
                    )
                    existing_setting.temperature = config_data.get("temperature", 0.0)
                    existing_setting.thinking_tokens = config_data.get(
                        "thinking_tokens"
                    )
                    existing_setting.is_active = True
                    existing_setting.updated_at = datetime.now(timezone.utc)
                    existing_setting.llm_metadata = {
                        "vertex_region": config_data.get("vertex_region"),
                        "vertex_project_id": config_data.get("vertex_project_id"),
                        "azure_endpoint": config_data.get("azure_endpoint"),
                        "azure_api_version": config_data.get("azure_api_version"),
                        "cot_model": config_data.get("cot_model", False),
                        "source_config_id": model_id,
                    }
                    updated_count += 1
                    logger.info(
                        f"Updated LLM setting for model: {config_data['model']} (ID: {existing_setting.id})"
                    )
                else:
                    llm_setting = LLMSetting(
                        id=model_id,
                        user_id=admin_user.id,
                        model=config_data["model"],
                        api_type=config_data["api_type"],
                        encrypted_api_key=encrypted_api_key,
                        base_url=config_data.get("base_url"),
                        max_retries=config_data.get("max_retries", 10),
                        max_message_chars=config_data.get("max_message_chars", 30000),
                        temperature=config_data.get("temperature", 0.0),
                        thinking_tokens=config_data.get("thinking_tokens"),
                        is_active=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                        llm_metadata={
                            "vertex_region": config_data.get("vertex_region"),
                            "vertex_project_id": config_data.get("vertex_project_id"),
                            "azure_endpoint": config_data.get("azure_endpoint"),
                            "azure_api_version": config_data.get("azure_api_version"),
                            "cot_model": config_data.get("cot_model", False),
                            "source_config_id": model_id,
                        },
                    )

                    db_session.add(llm_setting)
                    added_count += 1
                    logger.info(
                        f"Created LLM setting for model: {config_data['model']} (ID: {llm_setting.id})"
                    )

            if added_count > 0 or updated_count > 0:
                logger.info(
                    f"Added {added_count} new and updated {updated_count} existing admin LLM settings"
                )
            else:
                logger.info("No admin LLM settings changes needed")

            await db_session.commit()
            logger.info("Successfully seeded admin LLM settings")
        except Exception:
            raise


async def ensure_admin_llm_settings_seeded():
    """Ensure admin LLM settings are seeded (run once)."""
    global _seeding_done
    if not _seeding_done:
        try:
            await seed_admin_llm_settings()
            _seeding_done = True
        except Exception as e:
            logger.error(f"Error seeding admin LLM settings: {e}")
