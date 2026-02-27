"""Design Mode tool for structured AI style change output."""

from __future__ import annotations

from ii_agent.chat.schemas import ErrorTextContent, JsonResultContent

from ii_agent.chat.tools.base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .tooling import parse_tool_call_json

DESIGN_MODE_AI_CHANGE_TOOL_NAME = "submit_design_mode_ai_change"

_DESIGN_MODE_AI_CHANGE_PARAMETERS = {
    "type": "object",
    "properties": {
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "property": {
                        "type": "string",
                        "description": "CSS property name or 'textContent'.",
                    },
                    "value": {
                        "type": "string",
                        "description": "CSS value or new text content.",
                    },
                },
                "required": ["property", "value"],
            },
        },
        "explanation": {
            "type": "string",
            "description": "Brief explanation of the suggested changes.",
        },
    },
    "required": ["changes", "explanation"],
}


class DesignModeAIChangeTool(BaseTool):
    def __init__(self) -> None:
        self._name = DESIGN_MODE_AI_CHANGE_TOOL_NAME

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description="Return CSS/text changes for the selected element.",
            parameters=_DESIGN_MODE_AI_CHANGE_PARAMETERS,
            required=["changes", "explanation"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))
        return ToolResponse(output=JsonResultContent(value=payload))


__all__ = [
    "DESIGN_MODE_AI_CHANGE_TOOL_NAME",
    "DesignModeAIChangeTool",
]
