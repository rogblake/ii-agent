"""Repository for generic billable usage records."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.usage.models import UsageRecord


class UsageRecordRepository:
    """Data access layer for UsageRecord."""

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        billing_context: str = "unknown",
        subject_kind: str,
        subject_id: str | None,
        run_id: UUID | str | None,
        source_domain: str,
        billing_kind: str,
        credits_charged: Decimal | float,
        app_kind: str | None = None,
        tool_name: str | None = None,
        model_id: str | None = None,
        provider: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        latency_ms: int | None = None,
        cost_usd: Decimal | float | None = None,
        ledger_entry_id: int | None = None,
        usage_metadata: dict | None = None,
    ) -> UsageRecord:
        """Insert one usage record."""
        usage_record = UsageRecord(
            user_id=user_id,
            billing_context=billing_context,
            subject_kind=subject_kind,
            subject_id=subject_id,
            run_id=_coerce_uuid(run_id),
            source_domain=source_domain,
            billing_kind=billing_kind,
            app_kind=app_kind,
            tool_name=tool_name,
            model_id=model_id,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            latency_ms=latency_ms,
            cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
            credits_charged=Decimal(str(credits_charged)),
            ledger_entry_id=ledger_entry_id,
            usage_metadata=usage_metadata,
        )
        db.add(usage_record)
        await db.flush()
        return usage_record


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
