"""Repository for LLM invocation telemetry."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.usage.llm_invocation_models import LLMInvocation


class LLMInvocationRepository:
    """Data access layer for LLMInvocation."""

    async def create(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        request_kind: str,
        billing_context: str = "unknown",
        subject_kind: str = "session",
        subject_id: str | None = None,
        session_id: str | None = None,
        run_id: UUID | str | None = None,
        message_id: UUID | str | None = None,
        provider: str | None = None,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        latency_ms: int | None = None,
        cost_usd: Decimal | float | None = None,
        credits_charged: Decimal | float | None = None,
        success: bool = True,
        error_code: str | None = None,
        finish_reason: str | None = None,
    ) -> LLMInvocation:
        """Insert one invocation telemetry row."""
        resolved_subject_id = subject_id or session_id
        if resolved_subject_id is None:
            raise ValueError("subject_id or session_id is required for llm invocation telemetry")

        invocation = LLMInvocation(
            run_id=_coerce_uuid(run_id),
            user_id=user_id,
            billing_context=billing_context,
            subject_kind=subject_kind,
            subject_id=resolved_subject_id,
            message_id=_coerce_uuid(message_id),
            provider=provider,
            model=model,
            request_kind=request_kind,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            latency_ms=latency_ms,
            cost_usd=Decimal(str(cost_usd)) if cost_usd is not None else None,
            credits_charged=(
                Decimal(str(credits_charged)) if credits_charged is not None else None
            ),
            success=success,
            error_code=error_code,
            finish_reason=finish_reason,
        )
        db.add(invocation)
        await db.flush()
        return invocation


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
