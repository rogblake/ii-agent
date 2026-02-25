"""Design Mode tool: fetch SVG inner markup for an icon."""

from __future__ import annotations

from ii_agent.chat.schemas import ErrorTextContent, JsonResultContent
from ii_agent.design import lucide_catalog

from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .design_mode_iframe_ai_list_icons import _FALLBACK_LUCIDE_ICON_NAMES
from .design_mode_tooling import parse_tool_call_json


DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME = "get_icon_svg"


class DesignModeIframeAIGetIconSvgTool(BaseTool):
    def __init__(self) -> None:
        self._name = DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description="Get Lucide SVG inner markup for an icon name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Lucide icon name (e.g. 'rocket').",
                    }
                },
                "required": ["name"],
            },
            required=["name"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))

        name = payload.get("name") if isinstance(payload.get("name"), str) else ""

        try:
            svg_inner = lucide_catalog.get_icon_svg_inner(name)
        except Exception:
            svg_inner = None

        if svg_inner:
            return ToolResponse(output=JsonResultContent(value={"name": name, "svg_inner": svg_inner}))

        try:
            suggestions = lucide_catalog.list_icons(query=name, limit=15)
        except Exception:
            normalized = name.strip().lower()
            suggestions = [icon for icon in _FALLBACK_LUCIDE_ICON_NAMES if normalized in icon][:15]
        return ToolResponse(
            output=JsonResultContent(value={"error": "not_found", "suggestions": suggestions})
        )


__all__ = ["DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME", "DesignModeIframeAIGetIconSvgTool"]
