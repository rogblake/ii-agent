"""Repository for durable billing usage facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.outbox.models import BillingUsageFact


class BillingUsageFactRepository:
    """CRUD and claim helpers for billing usage facts."""

    async def insert_idempotent(
        self,
        db: AsyncSession,
        *,
        reservation_id: str,
        user_id: str,
        billing_kind: str,
        event_kind: str,
        session_id: str | None = None,
        run_id: UUID | str | None = None,
        message_id: UUID | str | None = None,
        app_kind: str | None = None,
        provider: str | None = None,
        request_kind: str | None = None,
        model_id: str | None = None,
        tool_name: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        latency_ms: int | None = None,
        cost_usd: Decimal | float | None = None,
    ) -> BillingUsageFact:
        stmt = pg_insert(BillingUsageFact).values(
            reservation_id=reservation_id,
            user_id=user_id,
            session_id=session_id,
            run_id=_coerce_uuid(run_id),
            message_id=_coerce_uuid(message_id),
            billing_kind=billing_kind,
            event_kind=event_kind,
            app_kind=app_kind,
            provider=provider,
            request_kind=request_kind,
            model_id=model_id,
            tool_name=tool_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            latency_ms=latency_ms,
            cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
        )
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["reservation_id"],
        ).returning(BillingUsageFact)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            return row

        existing = await db.execute(
            select(BillingUsageFact).where(
                BillingUsageFact.reservation_id == reservation_id
            )
        )
        return existing.scalar_one()

    async def lock_by_id(
        self,
        db: AsyncSession,
        fact_id: int,
    ) -> BillingUsageFact | None:
        result = await db.execute(
            select(BillingUsageFact)
            .where(BillingUsageFact.id == fact_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_dispatchable_locked(
        self,
        db: AsyncSession,
        *,
        stale_before: datetime,
        limit: int,
    ) -> list[BillingUsageFact]:
        result = await db.execute(
            select(BillingUsageFact)
            .where(
                (BillingUsageFact.status == "captured")
                | (
                    (BillingUsageFact.status == "processing")
                    & (BillingUsageFact.processing_started_at.isnot(None))
                    & (BillingUsageFact.processing_started_at < stale_before)
                )
            )
            .order_by(BillingUsageFact.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    return UUID(str(value))
