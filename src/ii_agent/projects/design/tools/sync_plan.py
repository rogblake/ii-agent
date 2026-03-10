"""Design Mode tool for source sync planning."""

from __future__ import annotations

from ii_agent.chat.types import ErrorTextContent, JsonResultContent

from ii_agent.chat.tools.base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .tooling import parse_tool_call_json

DESIGN_MODE_SYNC_PLAN_TOOL_NAME = "submit_design_mode_sync_plan"

_DESIGN_MODE_SYNC_PLAN_PARAMETERS = {
    "type": "object",
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "change_index": {
                        "type": "integer",
                        "description": "1-based index matching Change N in the prompt.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path under /workspace to modify.",
                        "pattern": "^/workspace/",
                    },
                    "change_type": {
                        "type": "string",
                        "description": "tailwind|css|inline|text",
                    },
                    "modifications": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "description": "Must be 'replace'.",
                                    "enum": ["replace"],
                                },
                                "old": {
                                    "type": "string",
                                    "description": "Exact string to find in the file.",
                                },
                                "new": {
                                    "type": "string",
                                    "description": "Exact replacement string.",
                                },
                            },
                            "required": ["type", "old", "new"],
                        },
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation (optional).",
                    },
                },
                "required": [
                    "change_index",
                    "file_path",
                    "change_type",
                    "modifications",
                ],
            },
        }
    },
    "required": ["changes"],
}


class DesignModeSyncPlanTool(BaseTool):
    def __init__(self) -> None:
        self._name = DESIGN_MODE_SYNC_PLAN_TOOL_NAME

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description=(
                "Return a structured plan describing how to apply each Design Mode change to "
                "the /workspace source files. Return a `changes` array containing one entry "
                "for every change_index."
            ),
            parameters=_DESIGN_MODE_SYNC_PLAN_PARAMETERS,
            required=["changes"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))
        return ToolResponse(output=JsonResultContent(value=payload))


__all__ = [
    "DESIGN_MODE_SYNC_PLAN_TOOL_NAME",
    "DesignModeSyncPlanTool",
]
