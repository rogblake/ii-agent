"""Backfill usage_records rows from credit_ledger deduction entries."""

from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ii_agent.billing.credits.ledger_models import CreditLedgerEntry
from ii_agent.billing.usage.models import UsageRecord
from ii_agent.core.db.manager import get_db_session_local


logger = logging.getLogger(__name__)

BATCH_SIZE = 500


async def backfill() -> None:
    """Populate usage_records for existing deduction ledger entries."""
    last_id = 0
    processed = 0
    inserted = 0

    async with get_db_session_local() as db:
        while True:
            result = await db.execute(
                select(CreditLedgerEntry)
                .where(
                    CreditLedgerEntry.id > last_id,
                    CreditLedgerEntry.entry_type == "deduction",
                )
                .order_by(CreditLedgerEntry.id)
                .limit(BATCH_SIZE)
            )
            entries = result.scalars().all()
            if not entries:
                break

            for entry in entries:
                meta = entry.entry_metadata or {}
                billing_kind = meta.get("billing_kind") or entry.source_domain or "unknown"
                stmt = (
                    pg_insert(UsageRecord)
                    .values(
                        user_id=entry.user_id,
                        session_id=meta.get("session_id") or entry.source_id,
                        run_id=_coerce_uuid(meta.get("run_id")),
                        ledger_entry_id=entry.id,
                        source_domain=entry.source_domain or billing_kind,
                        billing_kind=billing_kind,
                        app_kind=meta.get("app_kind"),
                        tool_name=meta.get("tool_name"),
                        model_id=meta.get("model_id"),
                        provider=meta.get("pricing_provider") or meta.get("provider"),
                        input_tokens=_to_int(meta.get("input_tokens"), default=0),
                        output_tokens=_to_int(meta.get("output_tokens"), default=0),
                        cache_read_tokens=_to_int(
                            meta.get("cache_read_tokens"),
                            default=0,
                        ),
                        cache_write_tokens=_to_int(
                            meta.get("cache_write_tokens")
                            or meta.get("cache_creation_tokens"),
                            default=0,
                        ),
                        reasoning_tokens=_to_int(
                            meta.get("reasoning_tokens"),
                            default=0,
                        ),
                        latency_ms=_to_int(meta.get("latency_ms")),
                        cost_usd=meta.get("direct_cost_usd") or meta.get("cost_usd"),
                        credits_charged=_credits_charged(entry),
                        usage_metadata=meta or None,
                        created_at=entry.created_at,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[UsageRecord.ledger_entry_id],
                        index_where=UsageRecord.ledger_entry_id.isnot(None),
                    )
                )
                insert_result = await db.execute(stmt)
                inserted += int(insert_result.rowcount or 0)
                processed += 1
                last_id = entry.id

            await db.commit()
            logger.info(
                "Backfilled usage_records through ledger id %s (%s processed, %s inserted)",
                last_id,
                processed,
                inserted,
            )

    logger.info(
        "Finished usage_records backfill (%s processed, %s inserted)",
        processed,
        inserted,
    )


def _credits_charged(entry: CreditLedgerEntry) -> Decimal:
    return abs(entry.delta_credits or Decimal("0")) + abs(
        entry.delta_bonus_credits or Decimal("0")
    )


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any, *, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(backfill())
