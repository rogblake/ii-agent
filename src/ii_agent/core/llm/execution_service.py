"""Shared LLM execution service for one-shot calls and tool loops."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid as _uuid_mod
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ii_agent.billing.types import BillingScope
from ii_agent.billing.exceptions import BillingSettlementFinalError
from ii_agent.billing.reservations.types import SourceDomain
from ii_agent.billing.usage.llm_invocation_repository import LLMInvocationRepository
from ii_agent.chat.llm import get_client
from ii_agent.chat.tools.base import ToolCallInput
from ii_agent.chat.types import (
    ContentPart,
    FinishReason,
    Message,
    MessageRole,
    RunResponseOutput,
    TextContent,
    ToolCall,
)
from ii_agent.chat.application.tool_service import ChatToolService
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.core.llm.token_record import TokenTracker

if TYPE_CHECKING:
    from ii_agent.chat.base import LLMClient
    from ii_agent.core.llm.billing_service import LLMBillingService, ReservedLLMCall
    from ii_agent.billing.usage.models import TokenUsage


logger = logging.getLogger(__name__)

_FORCE_FINAL_TOOL_PROMPT = (
    "Submit the final tool payload exactly once now. Do not reply with normal text."
)


@dataclass(frozen=True)
class LLMBillingContext:
    """Billing context for an LLM execution."""

    scope: BillingScope
    llm_config: LLMConfig
    model_id: str | None = None
    message_id: _uuid_mod.UUID | None = None
    requested_output_token_cap: int | None = None
    llm_source_domain: str | None = None
    tool_source_domain: str | None = None

    @property
    def user_id(self) -> str:
        return self.scope.user_id

    @property
    def session_id(self) -> str | None:
        return self.scope.session_id

    @property
    def subject_id(self) -> str:
        return self.scope.subject_id

    @property
    def run_id(self) -> _uuid_mod.UUID | str | None:
        return self.scope.run_id


@dataclass
class ToolLoopResult:
    """Result returned from non-streaming tool loop execution."""

    final_payload: dict[str, Any]
    conversation: list[Message]
    last_response: RunResponseOutput | None


class LLMExecutionService:
    """Reusable execution utilities for send-once and iterative tool loops."""

    def __init__(
        self,
        *,
        llm_billing: LLMBillingService | None = None,
        llm_invocation_repo: LLMInvocationRepository | None = None,
    ) -> None:
        self._llm_billing = llm_billing
        self._llm_invocation_repo = llm_invocation_repo

    @staticmethod
    def create_client(llm_config: LLMConfig) -> "LLMClient":
        """Create provider client from LLM config."""
        return get_client(llm_config)

    @staticmethod
    def new_message(
        *,
        role: MessageRole,
        session_id: str,
        parts: list[Any],
    ) -> Message:
        """Create in-memory message object for loop orchestration."""
        now = int(time.time() * 1000)
        return Message(
            id=_uuid_mod.uuid4(),
            role=role,
            session_id=session_id,
            parts=parts,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def parse_tool_input(raw_input: Any) -> dict[str, Any]:
        """Parse provider tool input into JSON object payload."""
        if isinstance(raw_input, dict):
            return raw_input
        if isinstance(raw_input, str):
            text = raw_input.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except Exception:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def extract_text_content(parts: list[ContentPart]) -> str:
        """Extract concatenated text content parts from a response."""
        chunks: list[str] = []
        for part in parts:
            if isinstance(part, TextContent):
                chunks.append(part.text)
        return "".join(chunks)

    @staticmethod
    def _merge_provider_options(
        caller: dict[str, Any] | None,
        reservation: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Merge caller-supplied provider options with reservation options.

        Reservation keys (e.g. max_output_tokens) take precedence, but
        caller keys (e.g. system_instruction) are preserved.
        """
        if not reservation:
            return caller
        if not caller:
            return reservation
        merged: dict[str, Any] = {}
        for key in set(caller) | set(reservation):
            c_val = caller.get(key)
            r_val = reservation.get(key)
            if isinstance(c_val, dict) and isinstance(r_val, dict):
                merged[key] = {**c_val, **r_val}
            elif r_val is not None:
                merged[key] = r_val
            else:
                merged[key] = c_val
        return merged

    async def send_once(
        self,
        *,
        client: "LLMClient",
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        provider_options: dict[str, Any] | None = None,
        billing_context: LLMBillingContext | None = None,
        usage_key: str | None = None,
    ) -> RunResponseOutput:
        """Send one request with reserve → execute → settle billing."""
        if usage_key is None:
            if billing_context is not None:
                raise ValueError(
                    "usage_key is required when billing_context is provided. "
                    "Pass a deterministic key to ensure idempotent billing."
                )
            usage_key = f"send_once:{_uuid_mod.uuid4().hex[:12]}"
        reservation = await self._reserve_if_needed(
            billing_context,
            messages,
            usage_key,
        )
        effective_options = self._merge_provider_options(
            provider_options,
            reservation.provider_options if reservation else None,
        )

        try:
            response = await client.send(
                messages=messages,
                tools=tools,
                provider_options=effective_options,
            )
        except Exception as exc:
            await self._release_reservation(billing_context, reservation, "provider_error")
            await self._record_llm_invocation_if_needed(
                usage=None,
                billing_context=billing_context,
                request_kind=usage_key,
                credits_charged=None,
                finish_reason=None,
                model=(
                    billing_context.model_id or billing_context.llm_config.model
                    if billing_context
                    else None
                ),
                success=False,
                error_code=_exception_error_code(exc),
            )
            raise

        usage = self._resolve_usage(response.usage, billing_context)
        billed_credits = await self._settle_if_needed(
            billing_context,
            reservation,
            usage,
            usage_key,
        )
        await self._record_llm_invocation_if_needed(
            usage=usage,
            billing_context=billing_context,
            request_kind=usage_key,
            credits_charged=billed_credits,
            finish_reason=response.finish_reason.value if response.finish_reason else None,
        )
        return response

    async def run_tool_loop_until_final(
        self,
        *,
        client: "LLMClient",
        session_id: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        final_tool_name: str,
        tool_registry: dict[str, Any],
        max_loops: int,
        force_final_once: bool = True,
        final_tool_prompt: str = _FORCE_FINAL_TOOL_PROMPT,
        billing_context: LLMBillingContext | None = None,
        provider_options: dict[str, Any] | None = None,
        usage_key_prefix: str | None = None,
    ) -> ToolLoopResult:
        """Run iterative tool loop until final payload is emitted."""
        conversation = list(messages)
        forced_once = False
        last_response: RunResponseOutput | None = None

        if usage_key_prefix is None and billing_context is not None:
            raise ValueError(
                "usage_key_prefix is required when billing_context is provided. "
                "Pass a deterministic prefix to ensure idempotent billing."
            )
        loop_id = usage_key_prefix or f"tool_loop:{_uuid_mod.uuid4().hex[:12]}"
        for step in range(max(1, max_loops)):
            usage_key = f"{loop_id}:step_{step}"

            reservation = await self._reserve_if_needed(
                billing_context,
                conversation,
                usage_key,
            )
            effective_options = self._merge_provider_options(
                provider_options,
                reservation.provider_options if reservation else None,
            )

            try:
                response = await client.send(
                    messages=conversation,
                    tools=tools,
                    provider_options=effective_options,
                )
            except Exception as exc:
                await self._release_reservation(billing_context, reservation, "provider_error")
                await self._record_llm_invocation_if_needed(
                    usage=None,
                    billing_context=billing_context,
                    request_kind=usage_key,
                    credits_charged=None,
                    finish_reason=None,
                    model=(
                        billing_context.model_id or billing_context.llm_config.model
                        if billing_context
                        else None
                    ),
                    success=False,
                    error_code=_exception_error_code(exc),
                )
                raise

            last_response = response
            usage = self._resolve_usage(response.usage, billing_context)
            billed_credits = await self._settle_if_needed(
                billing_context,
                reservation,
                usage,
                usage_key,
            )
            await self._record_llm_invocation_if_needed(
                usage=usage,
                billing_context=billing_context,
                request_kind=usage_key,
                credits_charged=billed_credits,
                finish_reason=response.finish_reason.value if response.finish_reason else None,
            )

            assistant_parts = list(response.content or [])
            conversation.append(
                self.new_message(
                    role=MessageRole.ASSISTANT,
                    session_id=session_id,
                    parts=assistant_parts,
                )
            )

            tool_calls = [
                part
                for part in assistant_parts
                if isinstance(part, ToolCall) and not part.provider_executed
            ]
            for call in tool_calls:
                if call.name == final_tool_name:
                    return ToolLoopResult(
                        final_payload=self.parse_tool_input(call.input),
                        conversation=conversation,
                        last_response=last_response,
                    )

            if not tool_calls:
                if force_final_once and not forced_once:
                    forced_once = True
                    conversation.append(
                        self.new_message(
                            role=MessageRole.USER,
                            session_id=session_id,
                            parts=[TextContent(text=final_tool_prompt)],
                        )
                    )
                    continue
                break

            tool_result_parts = []
            for call in tool_calls:
                tool = tool_registry.get(call.name)
                tool_input = call.input
                if not isinstance(tool_input, str):
                    tool_input = json.dumps(
                        self.parse_tool_input(tool_input),
                        ensure_ascii=False,
                        default=str,
                    )

                tool_reservation = await self._reserve_tool_if_needed(
                    billing_context=billing_context,
                    tool_registry=tool_registry,
                    tool_call=call,
                    tool_input=tool_input,
                )
                tool_result = await ChatToolService.execute_tool(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    tool_input=tool_input,
                    tool_registry=tool_registry,
                )
                is_tool_error = _is_tool_error(tool_result.output)
                if tool_reservation is None and tool is not None:
                    await self._record_zero_cost_tool_usage_if_needed(
                        billing_context=billing_context,
                        tool_name=call.name,
                        succeeded=not is_tool_error,
                    )
                elif is_tool_error:
                    await self._release_tool_reservation(
                        billing_context=billing_context,
                        reservation=tool_reservation,
                        reason="tool_error",
                    )
                else:
                    tool_result.credits_charged = await self._settle_tool_if_needed(
                        billing_context=billing_context,
                        reservation=tool_reservation,
                        tool_name=call.name,
                        actual_cost_usd=tool_result.cost_usd or 0.0,
                    )
                tool_result_parts.append(tool_result)

            if tool_result_parts:
                conversation.append(
                    self.new_message(
                        role=MessageRole.TOOL,
                        session_id=session_id,
                        parts=tool_result_parts,
                    )
                )

            if response.finish_reason not in {
                FinishReason.TOOL_USE,
                FinishReason.END_TURN,
                FinishReason.UNKNOWN,
            }:
                break

        return ToolLoopResult(
            final_payload={},
            conversation=conversation,
            last_response=last_response,
        )

    # ------------------------------------------------------------------
    # Reservation helpers
    # ------------------------------------------------------------------

    async def _reserve_if_needed(
        self,
        billing_context: LLMBillingContext | None,
        messages: list[Any],
        usage_key: str,
    ) -> "ReservedLLMCall | None":
        """Reserve credits before an LLM call. Returns None if not billable."""
        if not self._llm_billing or not billing_context:
            return None
        if billing_context.llm_config.is_user_model():
            return None

        try:
            async with get_db_session_local() as billing_db:
                return await self._llm_billing.reserve_chat_llm_call(
                    billing_db,
                    scope=billing_context.scope,
                    model_id=(billing_context.model_id or billing_context.llm_config.model),
                    llm_config=billing_context.llm_config,
                    messages=messages,
                    source_id=usage_key,
                    request_kind=usage_key,
                    requested_output_token_cap=billing_context.requested_output_token_cap,
                    source_domain=billing_context.llm_source_domain or SourceDomain.CHAT_LLM,
                )
        except Exception:
            # InsufficientCreditsError and BillingReconciliationRequiredError
            # propagate to the caller so they surface as user-facing errors.
            raise

    async def _settle_if_needed(
        self,
        billing_context: LLMBillingContext | None,
        reservation: "ReservedLLMCall | None",
        usage: "TokenUsage | None",
        usage_key: str,
    ) -> float | None:
        """Settle a reservation to actual usage after provider returns."""
        if not self._llm_billing or not billing_context or not reservation:
            return None
        if not usage:
            logger.error(
                "Missing usage for completed LLM call; marking reservation settlement_failed",
                extra={"reservation_id": reservation.hold.reservation_id},
            )
            await self._mark_settlement_failed(
                billing_context,
                reservation,
                "missing_usage",
            )
            return None

        try:
            token_record = TokenTracker.from_chat_usage(usage)
            async with get_db_session_local() as billing_db:
                result = await self._llm_billing.settle_llm_call(
                    billing_db,
                    scope=billing_context.scope,
                    reservation=reservation,
                    token_record=token_record,
                    provider=(
                        billing_context.llm_config.api_type.value
                        if billing_context.llm_config.api_type is not None
                        else None
                    ),
                    request_kind=usage_key,
                )
            if result and result.total_charged is not None:
                return float(result.total_charged)
            return None
        except Exception:
            logger.error(
                "Failed to settle LLM billing for subject %s; "
                "marking reservation settlement_failed",
                f"{billing_context.scope.subject.kind.value}:{billing_context.scope.subject.id}",
                exc_info=True,
            )
            await self._mark_settlement_failed(billing_context, reservation, "settle_exception")
            return None

    async def _mark_settlement_failed(
        self,
        billing_context: LLMBillingContext | None,
        reservation: "ReservedLLMCall | None",
        error: str,
    ) -> None:
        """Mark reservation as settlement_failed so it is not auto-expired."""
        if not self._llm_billing or not billing_context or not reservation:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.mark_settlement_failed(
                    billing_db,
                    reservation_id=reservation.hold.reservation_id,
                    error=error,
                )
        except Exception:
            logger.error(
                "Failed to mark reservation settlement_failed for subject %s",
                f"{billing_context.scope.subject.kind.value}:{billing_context.scope.subject.id}",
                exc_info=True,
            )
            raise BillingSettlementFinalError(
                (
                    "Failed to persist settlement_failed for reservation "
                    f"{reservation.hold.reservation_id}"
                ),
                reservation_id=reservation.hold.reservation_id,
            )

    async def _release_reservation(
        self,
        billing_context: LLMBillingContext | None,
        reservation: "ReservedLLMCall | None",
        reason: str,
    ) -> None:
        """Release a reservation without charging."""
        if not self._llm_billing or not billing_context or not reservation:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.release_llm_call(
                    billing_db,
                    reservation=reservation,
                    reason=reason,
                )
        except Exception:
            logger.warning(
                "Failed to release LLM reservation for subject %s",
                f"{billing_context.scope.subject.kind.value}:{billing_context.scope.subject.id}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_usage(
        self,
        usage: "TokenUsage | None",
        billing_context: LLMBillingContext | None,
    ) -> "TokenUsage | None":
        """Apply model fallback so billing and telemetry use the same resolved usage."""
        if not usage or not billing_context:
            return usage

        model_name = (
            usage.model_name or billing_context.model_id or billing_context.llm_config.model
        )
        if model_name and usage.model_name != model_name:
            return usage.model_copy(update={"model_name": model_name})
        return usage

    async def _record_llm_invocation_if_needed(
        self,
        *,
        usage: "TokenUsage | None",
        billing_context: LLMBillingContext | None,
        request_kind: str,
        credits_charged: float | None,
        finish_reason: str | None,
        model: str | None = None,
        success: bool = True,
        error_code: str | None = None,
    ) -> None:
        """Best-effort telemetry write for one LLM invocation."""
        if not self._llm_invocation_repo or not billing_context:
            return

        try:
            async with get_db_session_local() as telemetry_db:
                await self._llm_invocation_repo.create(
                    telemetry_db,
                    run_id=billing_context.run_id,
                    user_id=billing_context.user_id,
                    billing_context=billing_context.scope.billing_context,
                    subject_kind=billing_context.scope.subject.kind.value,
                    subject_id=billing_context.scope.subject.id,
                    message_id=billing_context.message_id,
                    provider=(
                        billing_context.llm_config.api_type.value
                        if billing_context.llm_config.api_type is not None
                        else None
                    ),
                    model=(
                        model
                        or (usage.model_name if usage else None)
                        or billing_context.model_id
                        or billing_context.llm_config.model
                    ),
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
                    credits_charged=_credits_decimal_or_none(credits_charged),
                    success=success,
                    error_code=error_code,
                    finish_reason=finish_reason,
                )
        except Exception:
            logger.warning(
                "Failed to write llm_invocation for %s:%s",
                billing_context.scope.subject.kind.value,
                billing_context.scope.subject.id,
                exc_info=True,
            )

    async def _record_zero_cost_tool_usage_if_needed(
        self,
        *,
        billing_context: LLMBillingContext | None,
        tool_name: str,
        succeeded: bool,
    ) -> None:
        """Write best-effort usage for unquoted zero-cost chat tools."""
        if not self._llm_billing or not billing_context:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.record_zero_cost_tool_usage(
                    billing_db,
                    scope=billing_context.scope,
                    tool_name=tool_name,
                    succeeded=succeeded,
                    source_domain=billing_context.tool_source_domain or SourceDomain.CHAT_TOOL,
                )
        except Exception:
            logger.debug(
                "Failed to record zero-cost tool usage for %s:%s",
                billing_context.scope.subject.kind.value,
                billing_context.scope.subject.id,
                exc_info=True,
            )

    async def _reserve_tool_if_needed(
        self,
        *,
        billing_context: LLMBillingContext | None,
        tool_registry: dict[str, Any],
        tool_call: ToolCall,
        tool_input: str,
    ):
        """Reserve credits for a billable chat tool used inside the loop."""
        if not self._llm_billing or not billing_context:
            return None

        tool = tool_registry.get(tool_call.name)
        if tool is None or not hasattr(tool, "quote_cost"):
            return None

        quote = await tool.quote_cost(
            ToolCallInput(
                id=tool_call.id,
                name=tool_call.name,
                input=tool_input,
            )
        )
        if quote is None:
            return None

        async with get_db_session_local() as billing_db:
            return await self._llm_billing.reserve_tool_call(
                billing_db,
                scope=billing_context.scope,
                source_domain=billing_context.tool_source_domain or SourceDomain.CHAT_TOOL,
                source_id=tool_call.id,
                tool_name=tool_call.name,
                quote=quote,
            )

    async def _settle_tool_if_needed(
        self,
        *,
        billing_context: LLMBillingContext | None,
        reservation,
        tool_name: str,
        actual_cost_usd: float,
    ) -> float | None:
        """Settle one reserved tool invocation to its final cost."""
        if not self._llm_billing or not billing_context or not reservation:
            return None

        try:
            async with get_db_session_local() as billing_db:
                result = await self._llm_billing.settle_tool_call(
                    billing_db,
                    scope=billing_context.scope,
                    reservation=reservation,
                    actual_cost_usd=actual_cost_usd,
                    provider=None,
                    latency_ms=None,
                    extra_usage_metadata={
                        "app_kind": billing_context.scope.app_kind,
                        "billing_context": billing_context.scope.billing_context,
                        "run_id": (
                            str(billing_context.scope.run_id)
                            if billing_context.scope.run_id is not None
                            else None
                        ),
                        "tool_name": tool_name,
                    },
                )
            if result and result.total_charged is not None:
                return float(result.total_charged)
            return None
        except Exception:
            logger.error(
                "Failed to settle tool billing for %s:%s; marking reservation settlement_failed",
                billing_context.scope.subject.kind.value,
                billing_context.scope.subject.id,
                exc_info=True,
            )
            await self._mark_tool_settlement_failed(
                billing_context=billing_context,
                reservation=reservation,
                error="tool_settle_exception",
            )
            return None

    async def _release_tool_reservation(
        self,
        *,
        billing_context: LLMBillingContext | None,
        reservation,
        reason: str,
    ) -> None:
        """Release a reserved tool invocation without charging."""
        if not self._llm_billing or not billing_context or not reservation:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.release_tool_call(
                    billing_db,
                    reservation=reservation,
                    reason=reason,
                )
        except Exception:
            logger.warning(
                "Failed to release tool reservation for %s:%s",
                billing_context.scope.subject.kind.value,
                billing_context.scope.subject.id,
                exc_info=True,
            )

    async def _mark_tool_settlement_failed(
        self,
        *,
        billing_context: LLMBillingContext | None,
        reservation,
        error: str,
    ) -> None:
        """Prevent auto-expiry refunds after a tool settle exception."""
        if not self._llm_billing or not billing_context or not reservation:
            return
        try:
            async with get_db_session_local() as billing_db:
                await self._llm_billing.mark_settlement_failed(
                    billing_db,
                    reservation_id=reservation.hold.reservation_id,
                    error=error,
                )
        except Exception:
            logger.error(
                "Failed to mark tool reservation settlement_failed for %s:%s",
                billing_context.scope.subject.kind.value,
                billing_context.scope.subject.id,
                exc_info=True,
            )
            raise BillingSettlementFinalError(
                (
                    "Failed to persist settlement_failed for tool reservation "
                    f"{reservation.hold.reservation_id}"
                ),
                reservation_id=reservation.hold.reservation_id,
            )


def _is_tool_error(output: Any) -> bool:
    return getattr(output, "type", None) in {
        "error-text",
        "error-json",
        "execution-denied",
    }


def _credits_decimal_or_none(value: float | Decimal | None) -> Decimal | None:
    if value in (None, 0, 0.0):
        return None
    return Decimal(str(value))


def _exception_error_code(exc: Exception) -> str:
    error_code = getattr(exc, "error_code", None)
    if error_code:
        return str(error_code)
    name = type(exc).__name__
    name = re.sub(r"(Error|Exception)$", "", name)
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return name.lower()
