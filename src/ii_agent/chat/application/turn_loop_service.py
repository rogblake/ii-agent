"""LLM turn loop service for managing the streaming LLM conversation loop."""

from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator, Dict, List, Any, TYPE_CHECKING

from ii_agent.chat.application.context_service import ContextWindowManager
from ii_agent.chat.messages.service import MessageService
from ii_agent.core.db import get_db_session_local
from ii_agent.chat.tools.base import ToolCallInput
from ii_agent.chat.types import (
    ToolCall,
    FinishReason,
    EventType,
    MessageRole,
    StorybookProgressContent,
    ToolResult,
)
from ii_agent.core.redis import cancel
from ii_agent.realtime.events.app_events import ModelUsageEvent, ToolUsageEvent
from ii_agent.settings.llm.schemas import ModelConfig

if TYPE_CHECKING:
    from ii_agent.chat.api.schemas import ChatMessageRequest
    from ii_agent.chat.types import Message, RunResponseOutput
    from ii_agent.chat.application.tool_service import ChatToolService
    from ii_agent.chat.tools.base import BaseTool
    from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub

logger = logging.getLogger(__name__)


class LLMTurnLoopService:
    """Service that runs the LLM turn loop: stream response, execute tools, repeat."""

    def __init__(
        self,
        *,
        message_service: MessageService,
        pubsub: AsyncIOPubSub | None = None,
    ) -> None:
        self._message_service = message_service
        self._pubsub = pubsub

    async def run(
        self,
        *,
        messages: List,
        provider,
        tool_registry: Dict[str, BaseTool],
        tools_to_pass: List[Dict[str, Any]],
        is_code_interpreter_enabled: bool,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        model_id: str,
        user_message: Message,
        run_id: str,
        model_config: ModelConfig,
        chat_request: ChatMessageRequest,
        tool_service: ChatToolService,
    ) -> AsyncIterator[Dict]:
        """Run the LLM turn loop.

        Acquires short-lived DB sessions only for DB operations, never holding
        a connection during LLM streaming or tool I/O.

        Yields SSE events for the frontend.
        """
        run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id

        while True:
            await cancel.raise_if_cancelled(run_id)

            # Context compression — short-lived DB session
            async with get_db_session_local() as db:
                messages = await ContextWindowManager.compress_context_if_needed(
                    db_session=db,
                    messages=messages,
                    session_id=session_id,
                    llm_config=model_config,
                    user_id=user_id,
                )

            # LLM streaming — NO DB connection held
            run_response: RunResponseOutput = None
            file_parts = []

            async for event in provider.stream(
                messages=messages,
                tools=tools_to_pass,
                is_code_interpreter_enabled=is_code_interpreter_enabled,
                session_id=session_id,
                provider_options=None,
            ):
                if event.type == EventType.COMPLETE:
                    run_response = event.response
                else:
                    sse_event = event.to_sse_event()
                    if sse_event is not None:
                        yield sse_event

            if run_response:
                yield {
                    "type": "usage",
                    "usage": {
                        "input_tokens": run_response.usage.input_tokens,
                        "output_tokens": run_response.usage.output_tokens,
                        "cache_read_tokens": run_response.usage.cache_read_tokens,
                        "cache_write_tokens": run_response.usage.cache_write_tokens,
                    },
                }

                # Publish ModelUsageEvent for credit deduction
                await self._publish_llm_usage(
                    run_response=run_response,
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_uuid,
                    model_config=model_config,
                )

            if run_response and run_response.files:
                file_parts.extend(run_response.files)

            await cancel.raise_if_cancelled(run_id)

            # Save assistant message — short-lived DB session
            async with get_db_session_local() as db:
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
                await db.commit()

            await cancel.raise_if_cancelled(run_id)

            messages.append(assistant_message)

            if run_response.finish_reason == FinishReason.TOOL_USE:
                tool_calls_to_execute = [
                    part
                    for part in run_response.content
                    if isinstance(part, ToolCall) and not part.provider_executed
                ]

                tool_result_parts = []
                use_storybook_polling = False

                # Tool execution — NO DB connection held
                for tool_call in tool_calls_to_execute:
                    tool = tool_registry.get(tool_call.name)

                    if (
                        tool
                        and tool_call.name == "generate_storybook"
                        and getattr(tool, "supports_streaming", False)
                        and len(tool_calls_to_execute) == 1
                        and hasattr(tool, "start_celery_generation")
                    ):
                        tool_response = await tool.start_celery_generation(
                            ToolCallInput(
                                id=tool_call.id,
                                name=tool_call.name,
                                input=tool_call.input,
                            ),
                            parent_message_id=user_message.id,
                            model_id=model_id,
                            run_id=run_id,
                            reservation_id=None,
                        )

                        if isinstance(tool_response.output, StorybookProgressContent):
                            use_storybook_polling = True
                            yield {
                                "type": "tool_progress",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.name,
                                "output": tool_response.output.model_dump(),
                            }
                            continue

                        tool_result = ToolResult(
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                            output=tool_response.output,
                            cost_usd=tool_response.cost_usd,
                        )
                    else:
                        tool_result = await tool_service.execute_tool(
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            tool_input=tool_call.input,
                            tool_registry=tool_registry,
                        )

                    yield {
                        "type": "tool_result",
                        "tool_call_id": tool_result.tool_call_id,
                        "name": tool_result.name,
                        "output": tool_result.output.model_dump(),
                    }

                    # Publish ToolUsageEvent for credit deduction
                    await self._publish_tool_usage(
                        tool_result=tool_result,
                        session_id=session_id,
                        user_id=user_id,
                        run_id=run_uuid,
                    )

                    tool_result_parts.append(tool_result)

                if use_storybook_polling:
                    # Post-response summarization — short-lived DB session
                    async with get_db_session_local() as db:
                        await ContextWindowManager.check_and_summarize_after_response(
                            db_session=db,
                            session_id=session_id,
                            llm_config=model_config,
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

                # Save tool results — short-lived DB session
                async with get_db_session_local() as db:
                    tool_results_message = await self._message_service.create_message(
                        db,
                        session_id=session_id,
                        role=MessageRole.TOOL,
                        parts=tool_result_parts,
                        parent_message_id=user_message.id,
                        model_id=chat_request.model_id,
                    )
                    await db.commit()

                messages.append(tool_results_message)
                continue

            # Post-response summarization — short-lived DB session
            async with get_db_session_local() as db:
                await ContextWindowManager.check_and_summarize_after_response(
                    db_session=db,
                    session_id=session_id,
                    llm_config=model_config,
                    user_id=user_id,
                )
                await db.commit()

            yield {
                "type": "complete",
                "message_id": assistant_message.id,
                "finish_reason": (
                    run_response.finish_reason.value if run_response.finish_reason else "end_turn"
                ),
                "files": file_parts,
            }
            break

    # ------------------------------------------------------------------
    # Billing event publishers
    # ------------------------------------------------------------------

    async def _publish_llm_usage(
        self,
        *,
        run_response: RunResponseOutput,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
        model_config: ModelConfig,
    ) -> None:
        """Publish ModelUsageEvent so CreditUsageHandler can deduct credits."""
        if not self._pubsub:
            return
        if not run_response.usage:
            return

        try:
            await self._pubsub.publish(
                ModelUsageEvent(
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_id,
                    setting_id=model_config.id,
                    model_id=model_config.model_id,
                    provider=model_config.provider,
                    pricing=model_config.pricing,
                    input_tokens=run_response.usage.input_tokens,
                    output_tokens=run_response.usage.output_tokens,
                    cache_read_tokens=run_response.usage.cache_read_tokens,
                    cache_write_tokens=run_response.usage.cache_write_tokens,
                    reasoning_tokens=run_response.usage.reasoning_tokens,
                    is_user_key=model_config.is_user_model(),
                )
            )
        except Exception:
            logger.exception(
                "Failed to publish LLM usage event (session=%s, model=%s)",
                session_id,
                model_config.model_id,
            )

    async def _publish_tool_usage(
        self,
        *,
        tool_result: ToolResult,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> None:
        """Publish ToolUsageEvent so CreditUsageHandler can deduct credits."""
        if not self._pubsub:
            return
        if not tool_result.cost_usd or tool_result.cost_usd <= 0:
            return

        try:
            await self._pubsub.publish(
                ToolUsageEvent(
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_id,
                    tool_name=tool_result.name,
                    cost_usd=tool_result.cost_usd,
                )
            )
        except Exception:
            logger.exception(
                "Failed to publish tool usage event (session=%s, tool=%s)",
                session_id,
                tool_result.name,
            )
