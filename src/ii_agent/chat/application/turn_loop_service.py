"""LLM turn loop service for managing the streaming LLM conversation loop."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Dict, List, Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

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
        llm_billing: Any = None,  # reserved for future billing integration
    ) -> None:
        self._message_service = message_service
        self._llm_billing = llm_billing

    async def run(
        self,
        db: AsyncSession,
        *,
        messages: List,
        provider,
        tool_registry: Dict[str, BaseTool],
        tools_to_pass: List[Dict[str, Any]],
        is_code_interpreter_enabled: bool,
        session_id: str,
        user_id: str,
        model_id: str,
        user_message: Message,
        run_id: str,
        llm_config: LLMConfig,
        chat_request: ChatMessageRequest,
        tool_service: ChatToolService,
    ) -> AsyncIterator[Dict]:
        """Run the LLM turn loop.

        Yields SSE events for the frontend.
        """
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

            if run_response.finish_reason == FinishReason.TOOL_USE:
                tool_calls_to_execute = [
                    part
                    for part in run_response.content
                    if isinstance(part, ToolCall) and not part.provider_executed
                ]

                tool_result_parts = []
                use_storybook_polling = False

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

                    tool_result_parts.append(tool_result)

                if use_storybook_polling:
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
                await db.commit()
                continue

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
                    run_response.finish_reason.value if run_response.finish_reason else "end_turn"
                ),
                "files": file_parts,
            }
            break
