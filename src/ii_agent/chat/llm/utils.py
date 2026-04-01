"""Lightweight LLM helper utilities.

"""

from __future__ import annotations

import uuid as _uuid_mod
from typing import Any

import logging

from ii_agent.chat.base import LLMClient
from ii_agent.chat.types import (
    ContentPart,
    FinishReason,
    Message,
    MessageRole,
    TextContent,
    ToolCall,
    ToolResult,
)

logger = logging.getLogger(__name__)


def make_message(
    *,
    role: MessageRole,
    session_id: str,
    parts: list[ContentPart],
) -> Message:
    """Build an in-memory ``Message`` with a fresh UUID."""
    return Message(
        id=_uuid_mod.uuid4(),
        role=role,
        session_id=session_id,
        parts=parts,
    )


def extract_text_content(parts: list[ContentPart]) -> str:
    """Join all ``TextContent`` parts into a single string."""
    return "\n".join(p.text for p in parts if isinstance(p, TextContent))


def parse_tool_input(raw: Any) -> dict[str, Any]:
    """Normalise raw tool input to a dict."""
    if isinstance(raw, dict):
        return raw
    return {}


class ToolLoopResult:
    """Result of a tool-calling loop."""

    __slots__ = ("final_payload", "messages")

    def __init__(self, final_payload: dict[str, Any], messages: list[Message]) -> None:
        self.final_payload = final_payload
        self.messages = messages


async def run_tool_loop(
    *,
    client: LLMClient,
    session_id: str,
    messages: list[Message],
    tools: list[Any],
    final_tool_name: str,
    tool_registry: dict[str, Any],
    max_loops: int = 10,
) -> ToolLoopResult:
    """Run an LLM tool-calling loop until ``final_tool_name`` is invoked.

    Each iteration sends the conversation to the provider, collects tool calls,
    executes them via ``tool_registry``, appends results, and repeats until
    the final tool is called or ``max_loops`` is reached.
    """
    conversation = list(messages)

    for loop_idx in range(max_loops):
        response = await client.send(conversation, tools=tools)

        # Build assistant message with the response
        assistant_msg = make_message(
            role=MessageRole.ASSISTANT,
            session_id=session_id,
            parts=response.content or [],
        )
        conversation.append(assistant_msg)

        # Collect tool calls from the response
        tool_calls = [p for p in (response.content or []) if isinstance(p, ToolCall)]
        if not tool_calls:
            break

        # Check for the final tool
        for tc in tool_calls:
            if tc.name == final_tool_name:
                payload = parse_tool_input(tc.input)
                return ToolLoopResult(final_payload=payload, messages=conversation)

        # Execute intermediate tools and append results
        result_parts: list[ContentPart] = []
        for tc in tool_calls:
            tool_impl = tool_registry.get(tc.name)
            if tool_impl is None:
                result_parts.append(
                    ToolResult(
                        tool_call_id=tc.tool_call_id or "",
                        output=f"Unknown tool: {tc.name}",
                    )
                )
                continue
            try:
                tool_input = parse_tool_input(tc.input)
                output = await tool_impl.execute(**tool_input)
                result_parts.append(
                    ToolResult(
                        tool_call_id=tc.tool_call_id or "",
                        output=output if isinstance(output, str) else str(output),
                    )
                )
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tc.name, exc)
                result_parts.append(
                    ToolResult(
                        tool_call_id=tc.tool_call_id or "",
                        output=f"Error: {exc}",
                    )
                )

        tool_msg = make_message(
            role=MessageRole.TOOL,
            session_id=session_id,
            parts=result_parts,
        )
        conversation.append(tool_msg)

    # Exhausted loops without final tool — return empty payload
    logger.warning("Tool loop exhausted %d iterations without final tool", max_loops)
    return ToolLoopResult(final_payload={}, messages=conversation)
