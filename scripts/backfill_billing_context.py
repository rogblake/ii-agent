"""Backfill billing_context values for existing billing rows."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from ii_agent.core.db.manager import get_db_session_local


logger = logging.getLogger(__name__)

BACKFILL_STATEMENTS = {
    "credit_reservations": text(
        """
        UPDATE credit_reservations
        SET billing_context = COALESCE(
            NULLIF(reservation_metadata->>'billing_context', ''),
            CASE
                WHEN source_domain = 'chat_llm' THEN 'chatloop'
                WHEN source_domain = 'agent_llm' THEN 'agentloop'
                WHEN source_domain IN ('chat_tool', 'agent_tool') AND tool_name = 'generate_storybook'
                    THEN 'storybook'
                WHEN source_domain IN ('chat_tool', 'agent_tool') THEN 'toolcall'
                WHEN source_domain IN ('voice_generation', 'image_generation') THEN 'storybook'
                ELSE 'unknown'
            END
        )
        WHERE billing_context IS NULL OR billing_context = 'unknown'
        """
    ),
    "usage_records": text(
        """
        UPDATE usage_records
        SET billing_context = COALESCE(
            NULLIF(usage_metadata->>'billing_context', ''),
            CASE
                WHEN source_domain = 'chat_llm' THEN 'chatloop'
                WHEN source_domain = 'agent_llm' THEN 'agentloop'
                WHEN source_domain IN ('chat_tool', 'agent_tool') AND tool_name = 'generate_storybook'
                    THEN 'storybook'
                WHEN source_domain IN ('chat_tool', 'agent_tool') THEN 'toolcall'
                WHEN source_domain IN ('voice_generation', 'image_generation') THEN 'storybook'
                ELSE 'unknown'
            END
        )
        WHERE billing_context IS NULL OR billing_context = 'unknown'
        """
    ),
    "llm_invocations": text(
        """
        UPDATE llm_invocations
        SET billing_context = CASE
            WHEN request_kind LIKE 'storybook_%' THEN 'storybook'
            WHEN request_kind LIKE 'nano_banana_%' THEN 'nanobanana'
            WHEN request_kind LIKE 'council_%' OR request_kind LIKE 'council:%' THEN 'council'
            WHEN request_kind LIKE 'design_%'
                OR request_kind LIKE 'project_design:%'
                OR request_kind LIKE 'projectdesign:%'
                THEN 'projectdesign'
            WHEN request_kind LIKE 'session_title%' THEN 'sessiontitle'
            WHEN request_kind LIKE 'enhance_prompt%' THEN 'enhanceprompt'
            WHEN request_kind LIKE 'factory%' THEN 'factory'
            WHEN request_kind = 'agent_llm' THEN 'agentloop'
            WHEN request_kind IN ('chat_turn', 'chat_response', 'chat_tool_use') THEN 'chatloop'
            ELSE 'unknown'
        END
        WHERE billing_context IS NULL OR billing_context = 'unknown'
        """
    ),
    "tool_invocations": text(
        """
        UPDATE tool_invocations
        SET billing_context = CASE
            WHEN tool_name = 'generate_storybook' THEN 'storybook'
            ELSE 'toolcall'
        END
        WHERE billing_context IS NULL OR billing_context = 'unknown'
        """
    ),
}


async def backfill() -> None:
    """Populate billing_context values for pre-squash billing rows."""
    async with get_db_session_local() as db:
        for table_name, statement in BACKFILL_STATEMENTS.items():
            result = await db.execute(statement)
            logger.info("Backfilled %s rows in %s", result.rowcount or 0, table_name)
        await db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(backfill())
