"""Shared LLM execution service for one-shot calls and tool loops."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.llm import get_client
from ii_agent.chat.schemas import (
    ContentPart,
    FinishReason,
    Message,
    MessageRole,
    RunResponseOutput,
    TextContent,
    ToolCall,
)
from ii_agent.chat.tool_service import ChatToolService
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.exceptions import PaymentRequiredError
from ii_agent.core.llm.token_record import TokenTracker

if TYPE_CHECKING:
    from ii_agent.chat.base import LLMClient
    from ii_agent.core.llm.billing_service import LLMBillingService
    from ii_agent.billing.usage.models import TokenUsage


logger = logging.getLogger(__name__)

_FORCE_FINAL_TOOL_PROMPT = (
    "Submit the final tool payload exactly once now. "
    "Do not reply with normal text."
)


@dataclass(frozen=True)
class LLMBillingContext:
    """Billing context for an LLM execution."""

    db: AsyncSession
    user_id: str
    session_id: str
    llm_config: LLMConfig
    model_id: str | None = None


@dataclass
class ToolLoopResult:
    """Result returned from non-streaming tool loop execution."""

    final_payload: dict[str, Any]
    conversation: list[Message]
    last_response: RunResponseOutput | None


class LLMExecutionService:
    """Reusable execution utilities for send-once and iterative tool loops."""

    def __init__(self, *, llm_billing: LLMBillingService | None = None) -> None:
        self._llm_billing = llm_billing

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
            id=uuid.uuid4(),
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

    async def send_once(
        self,
        *,
        client: "LLMClient",
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        provider_options: dict[str, Any] | None = None,
        billing_context: LLMBillingContext | None = None,
        usage_key: str = "send_once",
    ) -> RunResponseOutput:
        """Send one request and optionally bill based on returned usage."""
        response = await client.send(
            messages=messages, tools=tools, provider_options=provider_options
        )
        await self._bill_usage_if_needed(
            usage=response.usage,
            billing_context=billing_context,
            usage_key=usage_key,
            billed_usage_keys=None,
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
    ) -> ToolLoopResult:
        """Run iterative tool loop until final payload is emitted."""
        conversation = list(messages)
        forced_once = False
        billed_usage_keys: set[str] = set()
        last_response: RunResponseOutput | None = None

        for step in range(max(1, max_loops)):
            response = await client.send(messages=conversation, tools=tools)
            last_response = response
            await self._bill_usage_if_needed(
                usage=response.usage,
                billing_context=billing_context,
                usage_key=f"tool_loop_step_{step}",
                billed_usage_keys=billed_usage_keys,
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
                tool_input = call.input
                if not isinstance(tool_input, str):
                    tool_input = json.dumps(
                        self.parse_tool_input(tool_input),
                        ensure_ascii=False,
                        default=str,
                    )

                tool_result = await ChatToolService.execute_tool(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    tool_input=tool_input,
                    tool_registry=tool_registry,
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

    async def _bill_usage_if_needed(
        self,
        *,
        usage: "TokenUsage | None",
        billing_context: LLMBillingContext | None,
        usage_key: str,
        billed_usage_keys: set[str] | None,
    ) -> None:
        """Deduct credits for returned usage once per unique usage key."""
        if not self._llm_billing or not billing_context or not usage:
            return

        if billed_usage_keys is not None and usage_key in billed_usage_keys:
            return

        usage_for_billing = usage
        model_name = (
            usage.model_name
            or billing_context.model_id
            or billing_context.llm_config.model
        )
        if model_name and usage.model_name != model_name:
            usage_for_billing = usage.model_copy(update={"model_name": model_name})

        try:
            token_record = TokenTracker.from_chat_usage(usage_for_billing)
            await self._llm_billing.deduct_for_llm_usage(
                billing_context.db,
                user_id=billing_context.user_id,
                session_id=billing_context.session_id,
                token_record=token_record,
                is_user_model=billing_context.llm_config.is_user_model(),
            )
        except PaymentRequiredError:
            raise
        except Exception:
            logger.warning(
                "Failed to bill LLM usage for session %s",
                billing_context.session_id,
                exc_info=True,
            )
        finally:
            if billed_usage_keys is not None:
                billed_usage_keys.add(usage_key)
