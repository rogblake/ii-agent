"""System LLM settings seeding logic.

Seeds system-level LLM settings (user_id=NULL, config_type='system')
from ``Settings.model_configs``, populated by either:

- ``MODEL_CONFIGS`` env var (JSON array)
- ``MODEL_CONFIGS_FILE`` env var (YAML file, loaded via settings source)

Each entry is validated as ``ModelConfigEntry`` by the settings validator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from ii_agent.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_seeding_done = False


async def seed_admin_llm_settings() -> None:
    """Seed system-level LLM settings from Settings.model_configs."""
    from ii_agent.core.db import get_db_session_local
    from ii_agent.settings.llm.models import ModelSetting

    configs = get_settings().model_configs
    if not configs:
        logger.info("MODEL_CONFIGS not set, skipping system LLM seeding")
        return

    async with get_db_session_local() as db:
        result = await db.execute(
            select(ModelSetting).where(
                ModelSetting.user_id.is_(None),
                ModelSetting.config_type == "system",
            )
        )
        existing = {
            (s.model_id, s.provider): s for s in result.scalars().all()
        }
        logger.info(f"Found {len(existing)} existing system LLM settings")

        added = 0
        updated = 0

        for entry in configs:
            model_id = entry["model_id"]
            provider = entry["provider"]
            params = entry.get("params", {})

            encrypted_api_key = "empty"
            if entry.get("api_key"):
                from ii_agent.core.secrets.encryption import encryption_manager
                encrypted_api_key = encryption_manager.encrypt(entry["api_key"])

            pricing_raw = entry.get("pricing")
            pricing_dict = (
                pricing_raw.model_dump() if hasattr(pricing_raw, "model_dump") else pricing_raw
            ) if pricing_raw else None

            setting = existing.get((model_id, provider))

            if setting:
                setting.provider = provider
                setting.encrypted_api_key = encrypted_api_key
                setting.base_url = entry.get("base_url")
                setting.display_name = entry.get("display_name")
                setting.params = params
                setting.pricing = pricing_dict
                setting.is_default = entry.get("is_default", False)
                setting.updated_at = datetime.now(timezone.utc)
                updated += 1
                logger.info(f"Updated: {model_id} ({provider})")
            else:
                new_setting = ModelSetting(
                    model_id=model_id,
                    user_id=None,
                    provider=provider,
                    encrypted_api_key=encrypted_api_key,
                    base_url=entry.get("base_url"),
                    display_name=entry.get("display_name"),
                    params=params,
                    pricing=pricing_dict,
                    config_type="system",
                    is_default=entry.get("is_default", False),
                )
                db.add(new_setting)
                added += 1
                logger.info(f"Created: {model_id} ({provider})")

        if added or updated:
            logger.info(f"Seeded LLM settings: {added} added, {updated} updated")
        else:
            logger.info("No system LLM settings changes needed")

        await db.commit()


async def ensure_admin_llm_settings_seeded() -> None:
    """Ensure system LLM settings are seeded (run once)."""
    global _seeding_done
    if not _seeding_done:
        try:
            await seed_admin_llm_settings()
            _seeding_done = True
        except Exception as e:
            logger.error(f"Error seeding system LLM settings: {e}")
