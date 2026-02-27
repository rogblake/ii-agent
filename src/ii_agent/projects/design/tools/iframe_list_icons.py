"""Design Mode tool: list available icon names."""

from __future__ import annotations

from ii_agent.chat.schemas import ErrorTextContent, JsonResultContent
from ii_agent.projects.design.utils import lucide_catalog

from ii_agent.chat.tools.base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .tooling import parse_tool_call_json


DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME = "list_icons"

_FALLBACK_LUCIDE_ICON_NAMES: tuple[str, ...] = (
    "activity", "airplay", "alarm-clock", "alert-circle", "alert-triangle", "anchor",
    "archive", "arrow-down", "arrow-left", "arrow-right", "arrow-up", "at-sign",
    "award", "bell", "book", "bookmark", "briefcase", "building", "calendar", "camera",
    "check", "check-circle", "chevron-down", "chevron-left", "chevron-right", "chevron-up",
    "circle", "clock", "cloud", "code", "compass", "copy", "cpu", "credit-card",
    "download", "edit", "external-link", "eye", "file", "filter", "flag", "folder",
    "gift", "globe", "grid", "heart", "help-circle", "home", "image", "inbox", "info",
    "key", "layers", "layout", "lightbulb", "link", "list", "lock", "mail", "map-pin",
    "menu", "message-circle", "mic", "monitor", "moon", "more-horizontal", "more-vertical",
    "music", "navigation", "package", "paperclip", "pause", "pen", "phone", "play",
    "plus", "printer", "refresh-cw", "rocket", "save", "search", "send", "settings",
    "share", "shield", "shield-check", "shopping-cart", "star", "sun", "tag", "target",
    "thumbs-up", "trash", "unlock", "upload", "user", "users", "video", "volume-2",
    "wallet", "wifi", "x", "zap",
)


class DesignModeIframeAIListIconsTool(BaseTool):
    def __init__(self, *, max_icon_searches: int = 3) -> None:
        self._name = DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME
        self._icon_search_count = 0
        self._max_icon_searches = max(1, max_icon_searches)

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description="List available Lucide icon names (kebab-case).",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional substring filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 250,
                        "description": "Maximum icon names to return (default 50).",
                    },
                },
            },
            required=[],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))

        self._icon_search_count += 1
        query = payload.get("query") if isinstance(payload.get("query"), str) else None
        limit = payload.get("limit") if isinstance(payload.get("limit"), int) else 50

        try:
            icons = lucide_catalog.list_icons(query=query, limit=limit)
        except Exception:
            normalized = (query or "").strip().lower()
            if normalized:
                icons = [name for name in _FALLBACK_LUCIDE_ICON_NAMES if normalized in name][:limit]
            else:
                icons = list(_FALLBACK_LUCIDE_ICON_NAMES[:limit])

        if self._icon_search_count >= self._max_icon_searches:
            return ToolResponse(
                output=JsonResultContent(
                    value={
                        "icons": icons,
                        "note": (
                            f"Maximum {self._max_icon_searches} icon searches reached. "
                            "Please submit your plan now with the best match."
                        ),
                    }
                )
            )
        return ToolResponse(output=JsonResultContent(value={"icons": icons}))


__all__ = [
    "DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME",
    "DesignModeIframeAIListIconsTool",
    "_FALLBACK_LUCIDE_ICON_NAMES",
]
