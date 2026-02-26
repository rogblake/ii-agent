from __future__ import annotations

from ii_agent.llm.base import ToolParam

DESIGN_MODE_SYNC_PLAN_TOOL_NAME = "submit_design_mode_sync_plan"
DESIGN_MODE_SYNC_PLAN_TOOL = ToolParam(
    name=DESIGN_MODE_SYNC_PLAN_TOOL_NAME,
    description=(
        "Return a structured plan describing how to apply each Design Mode change to "
        "the /workspace source files. Call this tool ONCE with a `changes` array "
        "containing an entry for every change_index."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "change_index": {
                            "type": "integer",
                            "description": "1-based index matching the Change N in the prompt.",
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path under /workspace to modify (must start with /workspace/).",
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
                                        "description": "Exact string to find in the file (must match file contents).",
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
    },
)

DESIGN_MODE_AI_CHANGE_TOOL_NAME = "submit_design_mode_ai_change"
DESIGN_MODE_AI_CHANGE_TOOL = ToolParam(
    name=DESIGN_MODE_AI_CHANGE_TOOL_NAME,
    description=(
        "Return CSS/text changes for the selected element. Call this tool ONCE with "
        "`changes` and a short `explanation`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "property": {
                            "type": "string",
                            "description": "CSS property name (e.g. background-color) or 'textContent' for text changes.",
                        },
                        "value": {
                            "type": "string",
                            "description": "CSS value or new text when property is 'textContent'.",
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
    },
)

DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME = "search_design_mode_iframe_dom"
DESIGN_MODE_IFRAME_AI_SEARCH_TOOL = ToolParam(
    name=DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME,
    description=(
        "Search the current Design Mode iframe DOM snapshot for relevant elements. "
        "Use this to find the best target(s) when the selected element is not ideal."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text query."},
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Maximum number of results to return (default 10).",
            },
        },
        "required": ["query"],
    },
)

DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME = "get_design_mode_iframe_dom_node"
DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL = ToolParam(
    name=DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME,
    description=(
        "Get details for a specific element in the Design Mode iframe DOM snapshot by design_id."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "design_id": {
                "type": "string",
                "description": "The data-design-id of the element to fetch.",
            }
        },
        "required": ["design_id"],
    },
)

DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME = "list_icons"
DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL = ToolParam(
    name=DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME,
    description=(
        "List available Lucide icon names you can use (kebab-case). "
        "Use this to discover icons like 'rocket', 'zap', 'shield', etc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional substring filter (e.g. 'rocket' or 'arrow').",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 250,
                "description": "Maximum number of icon names to return (default 50).",
            },
        },
    },
)

DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME = "get_icon_svg"
DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL = ToolParam(
    name=DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME,
    description=(
        "Get Lucide SVG inner markup for an icon name (for replacing an existing <svg> content). "
        "Returns `svg_inner` suitable for assigning to svg.innerHTML."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Lucide icon name (e.g. 'rocket', 'shield-check').",
            }
        },
        "required": ["name"],
    },
)

DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME = "submit_design_mode_iframe_edit_plan"
DESIGN_MODE_IFRAME_AI_PLAN_TOOL = ToolParam(
    name=DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME,
    description=(
        "Return an ordered plan of edits to apply to the Design Mode iframe DOM. "
        "Call this tool ONCE when you are ready."
    ),
    input_schema={
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
    },
)

__all__ = [
    "DESIGN_MODE_SYNC_PLAN_TOOL_NAME",
    "DESIGN_MODE_SYNC_PLAN_TOOL",
    "DESIGN_MODE_AI_CHANGE_TOOL_NAME",
    "DESIGN_MODE_AI_CHANGE_TOOL",
    "DESIGN_MODE_IFRAME_AI_SEARCH_TOOL_NAME",
    "DESIGN_MODE_IFRAME_AI_SEARCH_TOOL",
    "DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL_NAME",
    "DESIGN_MODE_IFRAME_AI_GET_NODE_TOOL",
    "DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL_NAME",
    "DESIGN_MODE_IFRAME_AI_LIST_ICONS_TOOL",
    "DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL_NAME",
    "DESIGN_MODE_IFRAME_AI_GET_ICON_SVG_TOOL",
    "DESIGN_MODE_IFRAME_AI_PLAN_TOOL_NAME",
    "DESIGN_MODE_IFRAME_AI_PLAN_TOOL",
]
