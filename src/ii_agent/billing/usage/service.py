"""Usage tracking service — owns subject-linked usage tracking and history."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.credits.service import CreditService
from ii_agent.billing.types import BillingContextValue, SubjectKind
from ii_agent.billing.usage.models import SessionMetrics
from ii_agent.billing.usage.repository import MetricsRepository
from ii_agent.billing.usage.usage_record_repository import UsageRecordRepository

logger = logging.getLogger(__name__)


class UsageService:
    """Orchestrates credit deductions with subject-linked usage tracking.

    This service owns the cross-domain reads needed to resolve subject-linked
    usage into UI-facing history, while keeping the balance mutation logic out
    of ``CreditService``.
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

    async def record_settled_usage(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        billing_context: str | None,
        subject_kind: str,
        subject_id: str | None,
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
        """Record already-settled usage and update subject-linked metrics."""
        resolved_billing_context = (
            billing_context
            or (usage_metadata or {}).get("billing_context")
            or (BillingContextValue.default_for_app_kind(app_kind) if app_kind else None)
            or BillingContextValue.UNKNOWN
        )
        usage_record_id: int | None = None
        if self._usage_record_repo is not None:
            usage_record = await self._usage_record_repo.create(
                db,
                user_id=user_id,
                billing_context=resolved_billing_context,
                subject_kind=subject_kind,
                subject_id=subject_id,
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

        await self._accumulate_subject_usage(
            db,
            subject_kind=subject_kind,
            subject_id=subject_id,
            credits=-amount,
        )

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
            logger.error("Error accumulating session usage for %s", session_id, exc_info=True)
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
            logger.error("Error getting session usage for %s", session_id, exc_info=True)
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
        items, total, subject_title, total_credits = await self.get_subject_usage_detail(
            db,
            user_id=user_id,
            subject_kind=SubjectKind.SESSION.value,
            subject_id=session_id,
            page=page,
            per_page=per_page,
        )
        return items, total, subject_title or "", total_credits

    async def get_subject_usage_detail(
        self,
        db: AsyncSession,
        user_id: str,
        subject_kind: str,
        subject_id: str,
        *,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[dict], int, str | None, float]:
        """Get detailed usage breakdown for a specific billing subject."""
        from ii_agent.sessions.models import Session
        from ii_agent.billing.usage.models import UsageRecord

        subject_title = await self._resolve_subject_title(
            db,
            user_id=user_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            session_model=Session,
            usage_record_model=UsageRecord,
        )
        if subject_title is None:
            return [], 0, None, 0.0

        total_credits_result = await db.execute(
            select(func.coalesce(func.sum(UsageRecord.credits_charged), 0)).where(
                UsageRecord.subject_kind == subject_kind,
                UsageRecord.subject_id == subject_id,
                UsageRecord.user_id == user_id,
            )
        )
        total_credits = float(total_credits_result.scalar_one())

        count_result = await db.execute(
            select(func.count()).where(
                UsageRecord.subject_kind == subject_kind,
                UsageRecord.subject_id == subject_id,
                UsageRecord.user_id == user_id,
            )
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            select(UsageRecord)
            .where(
                UsageRecord.subject_kind == subject_kind,
                UsageRecord.subject_id == subject_id,
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
                "billing_context": r.billing_context,
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

        return items, total, subject_title, total_credits

    async def get_subject_history(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        subject_kind: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict], int]:
        """Get paginated credit usage history grouped by billing subject."""
        from ii_agent.sessions.models import Session
        from ii_agent.billing.usage.models import UsageRecord

        where_clauses = [
            UsageRecord.user_id == user_id,
            UsageRecord.subject_id.isnot(None),
        ]
        if subject_kind is not None:
            where_clauses.append(UsageRecord.subject_kind == subject_kind)

        grouped = (
            select(
                UsageRecord.subject_kind.label("subject_kind"),
                UsageRecord.subject_id.label("subject_id"),
                func.coalesce(func.sum(UsageRecord.credits_charged), 0).label("credits"),
                func.max(UsageRecord.created_at).label("updated_at"),
            )
            .where(*where_clauses)
            .group_by(UsageRecord.subject_kind, UsageRecord.subject_id)
            .subquery()
        )

        count_result = await db.execute(select(func.count()).select_from(grouped))
        total = count_result.scalar() or 0

        offset = (page - 1) * per_page
        result = await db.execute(
            select(
                grouped.c.subject_kind,
                grouped.c.subject_id,
                grouped.c.credits,
                grouped.c.updated_at,
            )
            .order_by(grouped.c.updated_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        rows = list(result.all())

        subject_titles = await self._resolve_history_subject_titles(
            db,
            user_id=user_id,
            rows=rows,
            session_model=Session,
        )

        history = [
            {
                "subject_kind": row.subject_kind,
                "subject_id": row.subject_id,
                "subject_title": subject_titles.get(
                    (row.subject_kind, row.subject_id), row.subject_id
                ),
                "credits": float(row.credits),
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
        return history, total

    async def get_history(
        self, db: AsyncSession, user_id: str, *, page: int = 1, per_page: int = 20
    ) -> tuple[list[dict], int]:
        """Legacy session-focused history wrapper over generic subject history."""
        subject_history, total = await self.get_subject_history(
            db,
            user_id,
            subject_kind=SubjectKind.SESSION.value,
            page=page,
            per_page=per_page,
        )
        history = [
            {
                "session_id": item["subject_id"],
                "session_title": item["subject_title"] or "Untitled Session",
                "credits": item["credits"],
                "updated_at": item["updated_at"],
            }
            for item in subject_history
        ]
        return history, total

    @staticmethod
    def _is_session_subject(subject_kind: str) -> bool:
        return subject_kind == SubjectKind.SESSION.value

    @classmethod
    def _subject_metadata(cls, *, subject_kind: str, subject_id: str) -> dict[str, Any]:
        if cls._is_session_subject(subject_kind):
            return {"session_id": subject_id}
        return {}

    async def _accumulate_subject_usage(
        self,
        db: AsyncSession,
        *,
        subject_kind: str,
        subject_id: str | None,
        credits: float,
    ) -> None:
        if not self._is_session_subject(subject_kind) or not subject_id:
            return
        await self.accumulate_session_usage(db, subject_id, credits)

    async def _resolve_subject_title(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        subject_kind: str,
        subject_id: str,
        session_model,
        usage_record_model,
    ) -> str | None:
        if self._is_session_subject(subject_kind):
            session_result = await db.execute(
                select(session_model.id, session_model.name).where(
                    session_model.id == subject_id,
                    session_model.user_id == user_id,
                )
            )
            session_row = session_result.one_or_none()
            if session_row is None:
                return None
            return session_row.name or "Untitled Session"

        exists_result = await db.execute(
            select(usage_record_model.id)
            .where(
                usage_record_model.subject_kind == subject_kind,
                usage_record_model.subject_id == subject_id,
                usage_record_model.user_id == user_id,
            )
            .limit(1)
        )
        if exists_result.scalar_one_or_none() is None:
            return None
        return subject_id

    async def _resolve_history_subject_titles(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        rows: list,
        session_model,
    ) -> dict[tuple[str, str | None], str]:
        titles = {
            (row.subject_kind, row.subject_id): (row.subject_id or "")
            for row in rows
            if row.subject_id is not None
        }
        session_ids = [
            row.subject_id
            for row in rows
            if self._is_session_subject(row.subject_kind) and row.subject_id
        ]
        if not session_ids:
            return titles

        session_rows = await db.execute(
            select(session_model.id, session_model.name).where(
                session_model.user_id == user_id,
                session_model.id.in_(session_ids),
            )
        )
        for row in session_rows:
            titles[(SubjectKind.SESSION.value, row.id)] = row.name or "Untitled Session"
        return titles
