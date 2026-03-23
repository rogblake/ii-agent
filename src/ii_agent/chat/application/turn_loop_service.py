"""LLM turn loop service for managing the streaming LLM conversation loop."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import AsyncIterator, Dict, List, Any, TYPE_CHECKING
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.billing.exceptions import BillingSettlementFinalError
from ii_agent.billing.reservations.types import SourceDomain
from ii_agent.billing.types import BillingContextValue, BillingScope
from ii_agent.billing.usage.llm_invocation_repository import LLMInvocationRepository
from ii_agent.billing.usage.tool_invocation_repository import ToolInvocationRepository
from ii_agent.chat.application.context_service import ContextWindowManager
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.tools.base import ToolCallInput
from ii_agent.chat.types import (
    ToolCall,
    FinishReason,
    EventType,
    MessageRole,
    StorybookProgressContent,
    ToolResult,
)
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.llm.token_record import TokenTracker
from ii_agent.core.redis import cancel

if TYPE_CHECKING:
    from ii_agent.chat.api.schemas import ChatMessageRequest
    from ii_agent.chat.types import Message, RunResponseOutput
    from ii_agent.chat.application.tool_service import ChatToolService
    from ii_agent.core.config.llm_config import LLMConfig
    from ii_agent.chat.tools.base import BaseTool

logger = logging.getLogger(__name__)


class LLMTurnLoopService:
    """Service that runs the LLM turn loop: stream response, execute tools, repeat."""

    def __init__(
        self,
        *,
        message_service: MessageService,
        llm_billing=None,
        llm_invocation_repo: LLMInvocationRepository | None = None,
        tool_invocation_repo: ToolInvocationRepository | None = None,
    ) -> None:
        self._message_service = message_service
        self._llm_billing = llm_billing
        self._llm_invocation_repo = llm_invocation_repo
        self._tool_invocation_repo = tool_invocation_repo

    async def run(
        self,
        db: AsyncSession,
        *,
        messages: List,
        provider,
        tool_registry: Dict[str, "BaseTool"],
        tools_to_pass: List[Dict[str, Any]],
        is_code_interpreter_enabled: bool,
        session_id: str,
        user_id: str,
        model_id: str,
        user_message: "Message",
        run_id: str,
        llm_config: "LLMConfig",
        chat_request: "ChatMessageRequest",
        tool_service: "ChatToolService",
    ) -> AsyncIterator[Dict]:
        """Run the LLM turn loop.

        Yields SSE events for the frontend.
        """
        llm_step_seq = 0
        while True:
            await cancel.raise_if_cancelled(run_id)

            messages = await ContextWindowManager.compress_context_if_needed(
                db_session=db,
                messages=messages,
                session_id=session_id,
                llm_config=llm_config,
                user_id=user_id,
            )

            run_response: RunResponseOutput = None
            file_parts = []
            llm_step_seq += 1
            llm_reservation = None
            provider_options = None

            if self._llm_billing and not llm_config.is_user_model():
                llm_reservation = await self._reserve_chat_llm_billing(
                    user_id=user_id,
                    session_id=session_id,
                    run_id=run_id,
                    model_id=model_id,
                    llm_config=llm_config,
                    messages=messages,
                    source_id=f"{run_id}:{llm_step_seq}",
                    request_kind="chat_turn",
                )
                provider_options = llm_reservation.provider_options if llm_reservation else None

            try:
                async for event in provider.stream(
                    messages=messages,
                    tools=tools_to_pass,
                    is_code_interpreter_enabled=is_code_interpreter_enabled,
                    session_id=session_id,
                    provider_options=provider_options,
                ):
                    if event.type == EventType.COMPLETE:
                        run_response = event.response
                    else:
                        sse_event = event.to_sse_event()
                        if sse_event is not None:
                            yield sse_event
            except Exception as exc:
                await self._record_llm_invocation(
                    db,
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    message_id=None,
                    provider=llm_config.api_type.value if llm_config else None,
                    model=model_id,
                    request_kind="chat_response",
                    billing_context=BillingContextValue.CHAT_LOOP,
                    usage=None,
                    finish_reason=None,
                    credits_charged=None,
                    success=False,
                    error_code=_exception_error_code(exc),
                )
                await self._release_chat_llm_billing(
                    reservation=llm_reservation,
                    reason="provider_error",
                )
                raise

            try:
                if run_response:
                    yield {
                        "type": "usage",
                        "usage": {
                            "input_tokens": run_response.usage.prompt_tokens,
                            "output_tokens": run_response.usage.completion_tokens,
                            "cache_creation_tokens": run_response.usage.cache_write_tokens,
                            "cache_read_tokens": run_response.usage.cache_read_tokens,
                        },
                    }

                if run_response and run_response.files:
                    file_parts.extend(run_response.files)

                await cancel.raise_if_cancelled(run_id)

                assistant_message = await self._message_service.create_message(
                    db,
                    session_id=session_id,
                    role=MessageRole.ASSISTANT,
                    parts=run_response.content,
                    model_id=model_id,
                    parent_message_id=user_message.id,
                    usage=run_response.usage,
                    file_ids=[f["id"] for f in file_parts],
                    provider_metadata=run_response.provider_metadata,
                    finish_reason=run_response.finish_reason.value
                    if run_response.finish_reason
                    else None,
                )

                await cancel.raise_if_cancelled(run_id)

                messages.append(assistant_message)

                billed_credits = None
                if self._llm_billing and llm_reservation:
                    record = (
                        TokenTracker.from_chat_usage(run_response.usage)
                        if run_response.usage is not None
                        else None
                    )
                    llm_settlement = await self._settle_chat_llm_billing(
                        reservation=llm_reservation,
                        user_id=user_id,
                        session_id=session_id,
                        run_id=run_id,
                        token_record=record,
                        provider=llm_config.api_type.value if llm_config else None,
                        request_kind=(
                            "chat_tool_use"
                            if run_response.finish_reason == FinishReason.TOOL_USE
                            else "chat_response"
                        ),
                        latency_ms=(
                            int(run_response.usage.response_time_ms)
                            if run_response.usage is not None
                            and run_response.usage.response_time_ms is not None
                            else None
                        ),
                    )
                    billed_credits = (
                        float(llm_settlement.total_charged) if llm_settlement is not None else None
                    )

                if run_response.finish_reason == FinishReason.TOOL_USE:
                    tool_calls_to_execute = [
                        part
                        for part in run_response.content
                        if isinstance(part, ToolCall) and not part.provider_executed
                    ]

                    tool_result_parts = []
                    use_storybook_polling = False

                    for tool_call in tool_calls_to_execute:
                        started_at = datetime.now(timezone.utc)
                        tool = tool_registry.get(tool_call.name)
                        tool_reservation = None

                        if (
                            tool
                            and tool_call.name == "generate_storybook"
                            and getattr(tool, "supports_streaming", False)
                            and len(tool_calls_to_execute) == 1
                            and hasattr(tool, "start_celery_generation")
                        ):
                            # Reserve before storybook generation
                            if self._llm_billing and tool is not None:
                                sb_quote = await tool.quote_cost(
                                    ToolCallInput(
                                        id=tool_call.id,
                                        name=tool_call.name,
                                        input=tool_call.input,
                                    )
                                )
                                tool_reservation = await self._reserve_chat_tool_billing(
                                    user_id=user_id,
                                    session_id=session_id,
                                    run_id=run_id,
                                    tool_call_id=tool_call.id,
                                    tool_name=tool_call.name,
                                    billing_context=self._tool_billing_context(tool_call.name),
                                    quote=sb_quote,
                                )

                            try:
                                tool_response = await tool.start_celery_generation(
                                    ToolCallInput(
                                        id=tool_call.id,
                                        name=tool_call.name,
                                        input=tool_call.input,
                                    ),
                                    parent_message_id=user_message.id,
                                    model_id=model_id,
                                    run_id=run_id,
                                    reservation_id=(
                                        tool_reservation.hold.reservation_id
                                        if tool_reservation is not None
                                        else None
                                    ),
                                )
                            except Exception:
                                await self._release_chat_tool_billing(
                                    reservation=tool_reservation,
                                    reason="storybook_launch_failed",
                                )
                                raise

                            if isinstance(tool_response.output, StorybookProgressContent):
                                use_storybook_polling = True
                                finished_at = datetime.now(timezone.utc)
                                await self._record_tool_invocation(
                                    db,
                                    run_id=run_id,
                                    session_id=session_id,
                                    user_id=user_id,
                                    message_id=assistant_message.id,
                                    tool_call_id=tool_call.id,
                                    tool_name=tool_call.name,
                                    billing_context=self._tool_billing_context(tool_call.name),
                                    started_at=started_at,
                                    finished_at=finished_at,
                                    tool_input=tool_call.input,
                                    output=tool_response.output,
                                    cost_usd=tool_response.cost_usd,
                                    credits_charged=None,
                                )
                                yield {
                                    "type": "tool_progress",
                                    "tool_call_id": tool_call.id,
                                    "name": tool_call.name,
                                    "output": tool_response.output.model_dump(),
                                }
                                continue

                            # Non-polling storybook result — settle inline
                            if self._llm_billing and tool_reservation is not None:
                                await self._settle_chat_tool_billing(
                                    reservation=tool_reservation,
                                    user_id=user_id,
                                    session_id=session_id,
                                    actual_cost_usd=tool_response.cost_usd or 0.0,
                                    run_id=run_id,
                                    tool_name=tool_call.name,
                                    billing_context=self._tool_billing_context(tool_call.name),
                                )
                            tool_result = ToolResult(
                                tool_call_id=tool_call.id,
                                name=tool_call.name,
                                output=tool_response.output,
                                cost_usd=tool_response.cost_usd,
                            )
                        else:
                            try:
                                if self._llm_billing and tool is not None:
                                    quote = await tool.quote_cost(
                                        ToolCallInput(
                                            id=tool_call.id,
                                            name=tool_call.name,
                                            input=tool_call.input,
                                        )
                                    )
                                    tool_reservation = await self._reserve_chat_tool_billing(
                                        user_id=user_id,
                                        session_id=session_id,
                                        run_id=run_id,
                                        tool_call_id=tool_call.id,
                                        tool_name=tool_call.name,
                                        billing_context=self._tool_billing_context(tool_call.name),
                                        quote=quote,
                                    )
                                tool_result = await tool_service.execute_tool(
                                    tool_call_id=tool_call.id,
                                    tool_name=tool_call.name,
                                    tool_input=tool_call.input,
                                    tool_registry=tool_registry,
                                )
                                if self._llm_billing and tool_reservation is not None:
                                    if _is_tool_error(tool_result.output):
                                        await self._release_chat_tool_billing(
                                            reservation=tool_reservation,
                                            reason="tool_error",
                                        )
                                    else:
                                        tool_settlement = await self._settle_chat_tool_billing(
                                            reservation=tool_reservation,
                                            user_id=user_id,
                                            session_id=session_id,
                                            actual_cost_usd=tool_result.cost_usd or 0.0,
                                            run_id=run_id,
                                            tool_name=tool_call.name,
                                            billing_context=self._tool_billing_context(
                                                tool_call.name
                                            ),
                                        )
                                        tool_result.credits_charged = (
                                            float(tool_settlement.total_charged)
                                            if tool_settlement is not None
                                            else None
                                        )
                            except Exception:
                                await self._release_chat_tool_billing(
                                    reservation=tool_reservation,
                                    reason="tool_failed",
                                )
                                raise

                        finished_at = datetime.now(timezone.utc)
                        await self._record_tool_invocation(
                            db,
                            run_id=run_id,
                            session_id=session_id,
                            user_id=user_id,
                            message_id=assistant_message.id,
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            billing_context=self._tool_billing_context(tool_call.name),
                            started_at=started_at,
                            finished_at=finished_at,
                            tool_input=tool_call.input,
                            output=tool_result.output,
                            cost_usd=tool_result.cost_usd,
                            credits_charged=tool_result.credits_charged,
                        )

                        yield {
                            "type": "tool_result",
                            "tool_call_id": tool_result.tool_call_id,
                            "name": tool_result.name,
                            "output": tool_result.output.model_dump(),
                        }

                        tool_result_parts.append(tool_result)

                    if use_storybook_polling:
                        await self._record_llm_invocation(
                            db,
                            run_id=run_id,
                            session_id=session_id,
                            user_id=user_id,
                            message_id=assistant_message.id,
                            provider=llm_config.api_type.value if llm_config else None,
                            model=run_response.usage.model_name or model_id,
                            request_kind="chat_tool_use",
                            billing_context=BillingContextValue.CHAT_LOOP,
                            usage=run_response.usage,
                            finish_reason=(
                                run_response.finish_reason.value
                                if run_response.finish_reason
                                else None
                            ),
                            credits_charged=billed_credits,
                        )

                        await ContextWindowManager.check_and_summarize_after_response(
                            db_session=db,
                            session_id=session_id,
                            llm_config=llm_config,
                            user_id=user_id,
                        )

                        await db.commit()

                        yield {
                            "type": "complete",
                            "message_id": assistant_message.id,
                            "finish_reason": run_response.finish_reason.value
                            if run_response.finish_reason
                            else "end_turn",
                            "files": file_parts,
                        }
                        break

                    tool_results_message = await self._message_service.create_message(
                        db,
                        session_id=session_id,
                        role=MessageRole.TOOL,
                        parts=tool_result_parts,
                        parent_message_id=user_message.id,
                        model_id=chat_request.model_id,
                    )

                    messages.append(tool_results_message)
                    await self._record_llm_invocation(
                        db,
                        run_id=run_id,
                        session_id=session_id,
                        user_id=user_id,
                        message_id=assistant_message.id,
                        provider=llm_config.api_type.value if llm_config else None,
                        model=run_response.usage.model_name or model_id,
                        request_kind="chat_tool_use",
                        billing_context=BillingContextValue.CHAT_LOOP,
                        usage=run_response.usage,
                        finish_reason=(
                            run_response.finish_reason.value if run_response.finish_reason else None
                        ),
                        credits_charged=billed_credits,
                    )
                    await db.commit()
                    continue

                await self._record_llm_invocation(
                    db,
                    run_id=run_id,
                    session_id=session_id,
                    user_id=user_id,
                    message_id=assistant_message.id,
                    provider=llm_config.api_type.value if llm_config else None,
                    model=run_response.usage.model_name or model_id,
                    request_kind="chat_response",
                    billing_context=BillingContextValue.CHAT_LOOP,
                    usage=run_response.usage,
                    finish_reason=(
                        run_response.finish_reason.value if run_response.finish_reason else None
                    ),
                    credits_charged=billed_credits,
                )

                await ContextWindowManager.check_and_summarize_after_response(
                    db_session=db,
                    session_id=session_id,
                    llm_config=llm_config,
                    user_id=user_id,
                )

                await db.commit()

                yield {
                    "type": "complete",
                    "message_id": assistant_message.id,
                    "finish_reason": (
                        run_response.finish_reason.value
                        if run_response.finish_reason
                        else "end_turn"
                    ),
                    "files": file_parts,
                }
                break
            except Exception:
                if run_response and llm_reservation:
                    record = (
                        TokenTracker.from_chat_usage(run_response.usage)
                        if run_response.usage is not None
                        else None
                    )
                    await self._settle_chat_llm_billing(
                        reservation=llm_reservation,
                        user_id=user_id,
                        session_id=session_id,
                        run_id=run_id,
                        token_record=record,
                        provider=llm_config.api_type.value if llm_config else None,
                        request_kind=(
                            "chat_tool_use"
                            if run_response.finish_reason == FinishReason.TOOL_USE
                            else "chat_response"
                        ),
                        latency_ms=(
                            int(run_response.usage.response_time_ms)
                            if run_response.usage is not None
                            and run_response.usage.response_time_ms is not None
                            else None
                        ),
                    )
                else:
                    await self._release_chat_llm_billing(
                        reservation=llm_reservation,
                        reason="post_provider_error",
                    )
                raise

    async def _reserve_chat_llm_billing(self, **kwargs):
        if self._llm_billing is None:
            return None
        async with get_db_session_local() as billing_db:
            session_id = kwargs.pop("session_id")
            user_id = kwargs.pop("user_id")
            run_id = kwargs.pop("run_id")
            return await self._llm_billing.reserve_chat_llm_call(
                billing_db,
                scope=BillingScope.for_session(
                    user_id=user_id,
                    app_kind="chat",
                    session_id=session_id,
                    billing_context=BillingContextValue.CHAT_LOOP,
                    run_id=run_id,
                ),
                **kwargs,
            )

    async def _settle_chat_llm_billing(self, **kwargs):
        if self._llm_billing is None:
            return None
        reservation = kwargs.get("reservation")
        token_record = kwargs.get("token_record")
        if token_record is None:
            reservation_id = getattr(
                getattr(reservation, "hold", None),
                "reservation_id",
                None,
            )
            logger.error(
                "Missing chat LLM usage; marking settlement_failed",
                extra={"reservation_id": reservation_id},
            )
            await self._mark_billing_settlement_failed(reservation_id, "chat_llm_missing_usage")
            return None
        try:
            async with get_db_session_local() as billing_db:
                session_id = kwargs.pop("session_id")
                user_id = kwargs.pop("user_id")
                run_id = kwargs.pop("run_id")
                return await self._llm_billing.settle_llm_call(
                    billing_db,
                    scope=BillingScope.for_session(
                        user_id=user_id,
                        app_kind="chat",
                        session_id=session_id,
                        billing_context=BillingContextValue.CHAT_LOOP,
                        run_id=run_id,
                    ),
                    **kwargs,
                )
        except Exception:
            reservation_id = getattr(
                getattr(reservation, "hold", None),
                "reservation_id",
                None,
            )
            logger.error(
                "Failed to settle chat LLM billing; marking settlement_failed",
                extra={"reservation_id": reservation_id},
                exc_info=True,
            )
            await self._mark_billing_settlement_failed(reservation_id, "chat_llm_settle_exception")
            return None

    async def _release_chat_llm_billing(self, *, reservation, reason: str) -> None:
        if self._llm_billing is None or reservation is None:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.release_llm_call(
                    billing_db,
                    reservation=reservation,
                    reason=reason,
                )
        except Exception:
            logger.warning("Failed to release chat LLM reservation", exc_info=True)

    async def _reserve_chat_tool_billing(
        self,
        *,
        user_id: str,
        session_id: str,
        run_id: str,
        tool_call_id: str,
        tool_name: str,
        billing_context: str,
        quote,
    ):
        if self._llm_billing is None:
            return None
        async with get_db_session_local() as billing_db:
            return await self._llm_billing.reserve_tool_call(
                billing_db,
                scope=BillingScope.for_session(
                    user_id=user_id,
                    app_kind="chat",
                    session_id=session_id,
                    billing_context=billing_context,
                    run_id=run_id,
                ),
                source_domain=SourceDomain.CHAT_TOOL,
                source_id=tool_call_id,
                tool_name=tool_name,
                quote=quote,
            )

    async def _settle_chat_tool_billing(
        self,
        *,
        reservation,
        user_id: str,
        session_id: str,
        actual_cost_usd: float,
        run_id: str,
        tool_name: str,
        billing_context: str,
    ):
        if self._llm_billing is None:
            return None
        try:
            async with get_db_session_local() as billing_db:
                return await self._llm_billing.settle_tool_call(
                    billing_db,
                    scope=BillingScope.for_session(
                        user_id=user_id,
                        app_kind="chat",
                        session_id=session_id,
                        billing_context=billing_context,
                        run_id=run_id,
                    ),
                    reservation=reservation,
                    actual_cost_usd=actual_cost_usd,
                    provider=None,
                    latency_ms=None,
                    extra_usage_metadata={
                        "app_kind": "chat",
                        "billing_context": billing_context,
                        "run_id": run_id,
                        "tool_name": tool_name,
                    },
                )
        except Exception:
            reservation_id = getattr(
                getattr(reservation, "hold", None),
                "reservation_id",
                None,
            )
            logger.error(
                "Failed to settle chat tool billing; marking settlement_failed",
                extra={"reservation_id": reservation_id},
                exc_info=True,
            )
            await self._mark_billing_settlement_failed(reservation_id, "chat_tool_settle_exception")
            return None

    async def _release_chat_tool_billing(self, *, reservation, reason: str) -> None:
        if self._llm_billing is None or reservation is None:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.release_tool_call(
                    billing_db,
                    reservation=reservation,
                    reason=reason,
                )
        except Exception:
            logger.warning("Failed to release chat tool reservation", exc_info=True)

    async def _mark_billing_settlement_failed(
        self,
        reservation_id: str | None,
        error: str,
    ) -> None:
        """Mark a reservation as settlement_failed to prevent auto-expiry refund."""
        if self._llm_billing is None or reservation_id is None:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.mark_settlement_failed(
                    billing_db,
                    reservation_id=reservation_id,
                    error=error,
                )
        except Exception:
            logger.error(
                "Failed to mark reservation %s as settlement_failed",
                reservation_id,
                exc_info=True,
            )
            raise BillingSettlementFinalError(
                f"Failed to persist settlement_failed for reservation {reservation_id}",
                reservation_id=reservation_id,
            )

    async def _record_llm_invocation(
        self,
        db: AsyncSession,
        *,
        run_id: str,
        session_id: str,
        user_id: str,
        message_id,
        provider: str | None,
        model: str | None,
        request_kind: str,
        billing_context: str,
        usage,
        finish_reason: str | None,
        credits_charged: float | None,
        success: bool = True,
        error_code: str | None = None,
    ) -> None:
        """Write one llm_invocations row without disrupting chat flow."""
        if not self._llm_invocation_repo:
            return

        try:
            async with db.begin_nested():
                await self._llm_invocation_repo.create(
                    db,
                    run_id=_coerce_uuid(run_id),
                    billing_context=billing_context,
                    session_id=session_id,
                    user_id=user_id,
                    message_id=message_id,
                    provider=provider,
                    model=model,
                    request_kind=request_kind,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    cache_read_tokens=usage.cache_read_tokens if usage else 0,
                    cache_write_tokens=usage.cache_write_tokens if usage else 0,
                    reasoning_tokens=usage.reasoning_tokens if usage else 0,
                    latency_ms=(
                        int(usage.response_time_ms)
                        if usage and usage.response_time_ms is not None
                        else None
                    ),
                    credits_charged=credits_charged or None,
                    success=success,
                    error_code=error_code,
                    finish_reason=finish_reason,
                )
        except Exception:
            logger.warning("Failed to write llm_invocation", exc_info=True)

    async def _record_tool_invocation(
        self,
        db: AsyncSession,
        *,
        run_id: str,
        session_id: str,
        user_id: str,
        message_id,
        tool_call_id: str,
        tool_name: str,
        billing_context: str,
        started_at: datetime,
        finished_at: datetime,
        tool_input: str | None,
        output,
        cost_usd: float | None = None,
        credits_charged: float | None = None,
    ) -> None:
        """Write one tool_invocations row without disrupting chat flow."""
        if not self._tool_invocation_repo:
            return

        is_error = _is_tool_error(output)
        output_summary = _truncate_text(_render_tool_output_summary(output))
        try:
            async with db.begin_nested():
                await self._tool_invocation_repo.create(
                    db,
                    run_id=_coerce_uuid(run_id),
                    billing_context=billing_context,
                    session_id=session_id,
                    user_id=user_id,
                    message_id=message_id,
                    provider_tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    tool_namespace="chat",
                    status="failed" if is_error else "completed",
                    started_at=started_at,
                    finished_at=finished_at,
                    latency_ms=int((finished_at - started_at).total_seconds() * 1000),
                    input_summary=_truncate_text(tool_input),
                    output_summary=output_summary,
                    is_error=is_error,
                    error_message=output_summary if is_error else None,
                    cost_usd=cost_usd,
                    credits_charged=credits_charged,
                )
        except Exception:
            logger.warning("Failed to write tool_invocation", exc_info=True)

    @staticmethod
    def _tool_billing_context(tool_name: str) -> str:
        if tool_name == "generate_storybook":
            return BillingContextValue.STORYBOOK
        return BillingContextValue.TOOL_CALL


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _is_tool_error(output: Any) -> bool:
    return getattr(output, "type", None) in {
        "error-text",
        "error-json",
        "execution-denied",
    }


def _render_tool_output_summary(output: Any) -> str:
    value = getattr(output, "value", output)
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _truncate_text(value: str | None, limit: int = 500) -> str | None:
    if not value:
        return None
    return value[:limit]


def _exception_error_code(exc: Exception) -> str:
    error_code = getattr(exc, "error_code", None)
    if error_code:
        return str(error_code)
    name = type(exc).__name__
    name = re.sub(r"(Error|Exception)$", "", name)
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return name.lower()
