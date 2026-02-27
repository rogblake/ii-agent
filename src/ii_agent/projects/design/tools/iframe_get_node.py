"""Design Mode tool: get iframe DOM node by design id."""

from __future__ import annotations

from ii_agent.chat.schemas import ErrorTextContent, JsonResultContent
from ii_agent.projects.design.schemas import IframeDocumentSnapshotNode

from ii_agent.chat.tools.base import BaseTool, ToolCallInput, ToolInfo, ToolResponse
from .iframe_search import _snapshot_nodes_by_id
from .tooling import parse_tool_call_json


DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME = "get_design_mode_iframe_dom_node"


class DesignModeIframeAIGetNodeTool(BaseTool):
    def __init__(self, snapshot_nodes: list[IframeDocumentSnapshotNode]) -> None:
        self._name = DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME
        self._snapshot_nodes = snapshot_nodes

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description="Get details for one iframe DOM node by data-design-id.",
            parameters={
                "type": "object",
                "properties": {
                    "design_id": {
                        "type": "string",
                        "description": "The target data-design-id.",
                    }
                },
                "required": ["design_id"],
            },
            required=["design_id"],
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        payload, error = parse_tool_call_json(tool_call)
        if error:
            return ToolResponse(output=ErrorTextContent(value=f"Invalid tool input: {error}"))

        nodes_by_id = _snapshot_nodes_by_id(self._snapshot_nodes)
        design_id = payload.get("design_id") if isinstance(payload.get("design_id"), str) else ""
        node = nodes_by_id.get(design_id)
        if not node:
            return ToolResponse(output=JsonResultContent(value={"error": "not_found"}))
        return ToolResponse(output=JsonResultContent(value={"node": node}))


__all__ = ["DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME", "DesignModeIframeAIGetNodeTool"]
