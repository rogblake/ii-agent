"""Shared helpers for Design Mode chat tools."""

from __future__ import annotations

import json
from typing import Any

from ii_agent.chat.tools.base import BaseTool, ToolCallInput


def parse_tool_call_json(tool_call: ToolCallInput) -> tuple[dict[str, Any], str | None]:
    try:
        payload = json.loads(tool_call.input) if tool_call.input else {}
    except Exception as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "tool input must be a JSON object"
    return payload, None


def tool_to_provider_definition(tool: BaseTool) -> dict[str, Any]:
    info = tool.info()
    return {
        "type": "function",
        "function": {
            "name": info.name,
            "description": info.description,
            "parameters": info.parameters,
        },
    }
