"""Design Mode tool: search iframe DOM snapshot."""

from __future__ import annotations

import re
from typing import Any

from ii_agent.chat.schemas import ErrorTextContent, JsonResultContent
from ii_agent.design.schemas import IframeDocumentSnapshotNode

from .base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .design_mode_tooling import parse_tool_call_json


DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME = "search_design_mode_iframe_dom"


class DesignModeIframeAISearchTool(BaseTool):
    def __init__(self, snapshot_nodes: list[IframeDocumentSnapshotNode]) -> None:
        self._name = DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME
        self._snapshot_nodes = snapshot_nodes

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description="Search the current Design Mode iframe DOM snapshot.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text query."},
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum results to return (default 10).",
                    },
                },
                "required": ["query"],
            },
            required=["query"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))

        nodes_by_id = _snapshot_nodes_by_id(self._snapshot_nodes)
        query = payload.get("query") if isinstance(payload.get("query"), str) else ""
        max_results = payload.get("max_results")
        if not isinstance(max_results, int):
            max_results = 10
        max_results = max(1, min(max_results, 50))
        if not query.strip():
            return ToolResponse(output=JsonResultContent(value={"results": []}))

        q_lower = query.strip().lower()
        tokens = _tokenize_dom_query(q_lower)
        scored: list[tuple[int, dict[str, Any]]] = []
        for node in nodes_by_id.values():
            design_id = node.get("designId") or ""
            tag = node.get("tagName") or ""
            class_name = node.get("className") or ""
            node_id = node.get("id") or ""
            text = node.get("textContent") or ""
            html = node.get("html") or ""
            attrs = node.get("attributes") or {}
            haystack = " ".join(
                [
                    str(design_id),
                    str(tag),
                    str(class_name),
                    str(node_id),
                    str(text),
                    str(html),
                    " ".join(str(value) for value in attrs.values()),
                ]
            ).lower()
            score = 0
            if q_lower in haystack:
                score += 8
            for token in tokens:
                if token in design_id.lower():
                    score += 6
                elif token in text.lower():
                    score += 5
                elif token in class_name.lower():
                    score += 3
                elif token in haystack:
                    score += 1
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, node in scored[:max_results]:
            results.append(
                {
                    "design_id": node.get("designId"),
                    "tag": node.get("tagName"),
                    "className": (node.get("className") or "")[:240],
                    "id": (node.get("id") or "")[:80],
                    "textContent": (node.get("textContent") or "")[:240],
                    "parentDesignId": node.get("parentDesignId"),
                    "score": score,
                }
            )
        return ToolResponse(output=JsonResultContent(value={"results": results}))


def _snapshot_nodes_by_id(
    snapshot_nodes: list[IframeDocumentSnapshotNode],
) -> dict[str, dict[str, Any]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in snapshot_nodes:
        design_id = (getattr(node, "designId", "") or "").strip()
        if not design_id:
            continue
        nodes_by_id[design_id] = {
            "designId": design_id,
            "tagName": (getattr(node, "tagName", "") or "").strip().lower(),
            "className": (getattr(node, "className", "") or "").strip(),
            "id": (getattr(node, "id", "") or "").strip(),
            "textContent": (getattr(node, "textContent", "") or "").strip(),
            "attributes": getattr(node, "attributes", {}) or {},
            "parentDesignId": (getattr(node, "parentDesignId", "") or "").strip() or None,
            "childDesignIds": [
                child
                for child in (getattr(node, "childDesignIds", None) or [])
                if isinstance(child, str) and child
            ],
            "html": getattr(node, "html", "") or "",
        }
    return nodes_by_id


def _tokenize_dom_query(query: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9#_\-]+", query.lower()) if token]


__all__ = ["DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME", "DesignModeIframeAISearchTool"]
