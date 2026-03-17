"""Usage tracking service — owns session-level credit accumulation and history."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import func, join, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.service import CreditDeductionResult, CreditService
from ii_agent.billing.reservations.types import BillingKind
from ii_agent.billing.usage.models import SessionMetrics
from ii_agent.billing.usage.repository import MetricsRepository
from ii_agent.billing.usage.usage_record_repository import UsageRecordRepository

logger = logging.getLogger(__name__)


class UsageService:
    """Orchestrates credit deductions with session-level usage tracking.

    This service owns the cross-domain join between ``SessionMetrics``
    and ``Session`` — keeping that concern out of ``CreditService``.
    """

    def __init__(
        self,
        *,
        credit_service: CreditService,
        metrics_repo: Optional[MetricsRepository] = None,
        usage_record_repo: Optional[UsageRecordRepository] = None,
    ) -> None:
        self._credit_service = credit_service
        self._metrics_repo = metrics_repo or MetricsRepository()
        self._usage_record_repo = usage_record_repo

    async def require_billing_ok(self, db: AsyncSession, user_id: str) -> None:
        """Raise if the account is blocked by billing reconciliation."""
        await self._credit_service.require_billing_ok(db, user_id)

    # ------------------------------------------------------------------
    # Deduct + track
    # ------------------------------------------------------------------

    async def deduct_and_track_session_usage(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
        amount: float,
        model_id: Optional[str] = None,
        source_domain: str = BillingKind.LLM_USAGE,
        idempotency_key: Optional[str] = None,
        entry_metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Deduct credits and record usage against a session.

        Returns ``True`` if deduction/tracking completed or amount <= 0.
        Returns ``False`` when deduction fails (insufficient balance, missing user).
        """
        if amount <= 0:
            return True

        metadata: dict[str, Any] = {"session_id": session_id}
        if entry_metadata:
            metadata.update(entry_metadata)
        if model_id:
            metadata["model_id"] = model_id

        result = await self._credit_service.deduct(
            db,
            user_id,
            amount,
            source_domain=source_domain,
            source_id=session_id,
            entry_metadata=metadata,
            idempotency_key=idempotency_key,
        )
        if result is False:
            return False

        # result is None → duplicate idempotency key, already charged.
        # Skip session metrics accumulation to avoid double-counting.
        if result is None:
            return True

        if isinstance(result, CreditDeductionResult) and self._usage_record_repo is not None:
            billing_kind = metadata.get("billing_kind") or source_domain
            await self._usage_record_repo.create(
                db,
                user_id=user_id,
                session_id=session_id,
                run_id=metadata.get("run_id"),
                source_domain=source_domain,
                billing_kind=billing_kind,
                app_kind=metadata.get("app_kind"),
                tool_name=metadata.get("tool_name"),
                model_id=model_id,
                provider=metadata.get("pricing_provider") or metadata.get("provider"),
                input_tokens=metadata.get("input_tokens", 0),
                output_tokens=metadata.get("output_tokens", 0),
                cache_read_tokens=metadata.get("cache_read_tokens", 0),
                cache_write_tokens=metadata.get("cache_write_tokens", 0),
                reasoning_tokens=metadata.get("reasoning_tokens", 0),
                latency_ms=metadata.get("latency_ms"),
                cost_usd=metadata.get("direct_cost_usd") or metadata.get("cost_usd"),
                credits_charged=result.total_charged,
                ledger_entry_id=result.ledger_entry_id,
                usage_metadata=metadata,
            )

        await self.accumulate_session_usage(db, session_id, -amount)
        return True

    async def record_settled_usage(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str | None,
        run_id,
        amount: float,
        source_domain: str,
        billing_kind: str,
        ledger_entry_id: int | None = None,
        model_id: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        latency_ms: int | None = None,
        cost_usd: float | None = None,
        usage_metadata: dict[str, Any] | None = None,
        app_kind: str | None = None,
    ) -> int | None:
        """Record already-settled usage and update session metrics."""
        usage_record_id: int | None = None
        if self._usage_record_repo is not None:
            usage_record = await self._usage_record_repo.create(
                db,
                user_id=user_id,
                session_id=session_id,
                run_id=run_id,
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
                cost_usd=cost_usd,
                credits_charged=Decimal(str(amount)),
                ledger_entry_id=ledger_entry_id,
                usage_metadata=usage_metadata,
            )
            usage_record_id = usage_record.id

        if session_id:
            await self.accumulate_session_usage(db, session_id, -amount)

        return usage_record_id

    # ------------------------------------------------------------------
    # Session usage accumulation
    # ------------------------------------------------------------------

    async def accumulate_session_usage(
        self, db: AsyncSession, session_id: str, credits: float
    ) -> None:
        """Accumulate credits consumed for a session.

        Credits should be passed as **negative** values to represent
        consumption.  Uses ``INSERT … ON CONFLICT DO UPDATE`` to atomically
        create-or-increment in one statement.
        """
        import uuid as _uuid
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        dec_credits = Decimal(str(credits))
        try:
            stmt = pg_insert(SessionMetrics).values(
                id=str(_uuid.uuid4()),
                session_id=session_id,
                credits=dec_credits,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_id"],
                set_={
                    "credits": SessionMetrics.credits + dec_credits,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)
            await db.flush()
            logger.debug("Accumulated %.4f credits for session %s", credits, session_id)
        except Exception:
            logger.error(
                "Error accumulating session usage for %s", session_id, exc_info=True
            )
            raise

    async def get_session_usage(
        self, db: AsyncSession, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return credit metrics for a session, or ``None``."""
        try:
            metrics = await self._metrics_repo.get_by_session_id(db, session_id)
            if metrics:
                return {
                    "session_id": metrics.session_id,
                    "credits": metrics.credits,
                    "created_at": metrics.created_at,
                    "updated_at": metrics.updated_at,
                }
            return None
        except Exception:
            logger.error(
                "Error getting session usage for %s", session_id, exc_info=True
            )
            raise

    # ------------------------------------------------------------------
    # Session-based credit history
    # ------------------------------------------------------------------

    async def get_session_usage_detail(
        self,
        db: AsyncSession,
        user_id: str,
        session_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict], int, str, float]:
        """Get detailed usage breakdown for a specific session.

        Returns (items, total_count, session_title, total_credits).
        """
        from ii_agent.sessions.models import Session
        from ii_agent.billing.usage.models import UsageRecord

        # Verify session belongs to user and get title
        session_result = await db.execute(
            select(Session.id, Session.name).where(
                Session.id == session_id,
                Session.user_id == user_id,
            )
        )
        session_row = session_result.one_or_none()
        if session_row is None:
            return [], 0, "", 0.0

        session_title = session_row.name or "Untitled Session"

        # Get total credits from SessionMetrics (authoritative)
        metrics_result = await db.execute(
            select(SessionMetrics.credits).where(
                SessionMetrics.session_id == session_id,
            )
        )
        total_credits_row = metrics_result.scalar_one_or_none()
        total_credits = float(total_credits_row) if total_credits_row is not None else 0.0

        # Count total records
        count_result = await db.execute(
            select(func.count()).where(
                UsageRecord.session_id == session_id,
                UsageRecord.user_id == user_id,
            )
        )
        total = count_result.scalar() or 0

        # Fetch paginated usage records
        offset = (page - 1) * per_page
        result = await db.execute(
            select(UsageRecord)
            .where(
                UsageRecord.session_id == session_id,
                UsageRecord.user_id == user_id,
            )
            .order_by(UsageRecord.created_at.asc())
            .limit(per_page)
            .offset(offset)
        )
        records = result.scalars().all()

        items = [
            {
                "id": r.id,
                "billing_kind": r.billing_kind,
                "source_domain": r.source_domain,
                "model_id": r.model_id,
                "tool_name": r.tool_name,
                "provider": r.provider,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cache_read_tokens": r.cache_read_tokens,
                "cache_write_tokens": r.cache_write_tokens,
                "reasoning_tokens": r.reasoning_tokens,
                "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                "credits_charged": float(r.credits_charged),
                "created_at": r.created_at,
            }
            for r in records
        ]

        return items, total, session_title, total_credits

    async def get_history(
        self, db: AsyncSession, user_id: str, *, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Get paginated credit usage history for a user.

        Joins ``SessionMetrics`` with ``Session`` — this cross-domain
        read is owned here rather than in ``CreditService``.
        """
        from ii_agent.sessions.models import Session

        base_query = (
            select(
                Session.id.label("session_id"),
                Session.name.label("session_title"),
                SessionMetrics.credits,
                SessionMetrics.updated_at,
            )
            .select_from(
                join(SessionMetrics, Session, SessionMetrics.session_id == Session.id)
            )
            .where(Session.user_id == user_id)
        )

        count_result = await db.execute(
            select(func.count())
            .select_from(
                join(SessionMetrics, Session, SessionMetrics.session_id == Session.id)
            )
            .where(Session.user_id == user_id)
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            base_query.order_by(SessionMetrics.updated_at.desc())
            .limit(per_page)
            .offset(offset)
        )

        history = [
            {
                "session_id": row.session_id,
                "session_title": row.session_title or "Untitled Session",
                "credits": float(row.credits),
                "updated_at": row.updated_at,
            }
            for row in result
        ]
        return history, total
