"""Builtin skills syncing logic.

Extracted from core/db/manager.py to keep infrastructure code
free of domain-specific business logic.
"""

from ii_agent.core.logger import logger


_skills_synced = False


async def ensure_builtin_skills_synced():
    """Ensure builtin skills are synced to database (run once)."""
    global _skills_synced
    if not _skills_synced:
        try:
            from ii_agent.engine.runtime.skills.loader import sync_builtin_to_db
            from ii_agent.core.db.manager import get_db

            async with get_db() as db_session:
                count = await sync_builtin_to_db(db_session)
                logger.info(f"Synced {count} builtin skills to database")
            _skills_synced = True
        except Exception as e:
            logger.error(f"Error syncing builtin skills: {e}")
