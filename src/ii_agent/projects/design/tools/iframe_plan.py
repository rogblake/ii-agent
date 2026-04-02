"""Design Mode tool for iframe DOM edit planning."""

from __future__ import annotations

from ii_agent.chat.types import ErrorTextContent, JsonResultContent

from ii_agent.chat.tools.base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .tooling import parse_tool_call_json

DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME = "submit_design_mode_iframe_edit_plan"

_DESIGN_MODE_IFRAME_AI_PLAN_PARAMETERS = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "description": "Ordered operations to apply.",
            "items": {
                "type": "object",
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": [
                            "set_style",
                            "set_text",
                            "set_icon",
                            "move",
                            "swap",
                        ],
                    },
                    "design_id": {"type": "string"},
                    "property": {"type": "string"},
                    "value": {"type": "string"},
                    "text": {"type": "string"},
                    "icon_name": {"type": "string"},
                    "svg_inner": {"type": "string"},
                    "anchor": {"type": "string"},
                    "target_design_id": {"type": "string"},
                },
                "required": ["op", "design_id"],
            },
        },
        "explanation": {
            "type": "string",
            "description": "Short explanation to show the user.",
        },
    },
    "required": ["operations", "explanation"],
}


class DesignModeIframeAIPlanTool(BaseTool):
    def __init__(self) -> None:
        self._name = DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description="Return an ordered plan of edits for the Design Mode iframe DOM.",
            parameters=_DESIGN_MODE_IFRAME_AI_PLAN_PARAMETERS,
            required=["operations", "explanation"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))
        return ToolResponse(output=JsonResultContent(value=payload))


__all__ = [
    "DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME",
    "DesignModeIframeAIPlanTool",
]
