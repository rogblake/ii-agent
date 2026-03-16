"""Repository for tool invocation telemetry."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.usage.tool_invocation_models import ToolInvocation


class ToolInvocationRepository:
    """Data access layer for ToolInvocation."""

    async def create(
        self,
        db: AsyncSession,
        *,
        session_id: str,
        user_id: str,
        tool_name: str,
        status: str,
        run_id: UUID | str | None = None,
        message_id: UUID | str | None = None,
        provider_tool_call_id: str | None = None,
        tool_namespace: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        latency_ms: int | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        is_error: bool = False,
        error_message: str | None = None,
        cost_usd: float | None = None,
        credits_charged: float | None = None,
    ) -> ToolInvocation:
        """Insert one tool execution telemetry row."""
        invocation = ToolInvocation(
            run_id=_coerce_uuid(run_id),
            session_id=session_id,
            user_id=user_id,
            message_id=_coerce_uuid(message_id),
            provider_tool_call_id=provider_tool_call_id,
            tool_name=tool_name,
            tool_namespace=tool_namespace,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            input_summary=input_summary,
            output_summary=output_summary,
            is_error=is_error,
            error_message=error_message,
            cost_usd=cost_usd,
            credits_charged=credits_charged,
        )
        db.add(invocation)
        await db.flush()
        return invocation


def _coerce_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    return UUID(str(value))
