"""Manifest loading/parsing for source-mapping sync."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ii_agent.projects.design.source_mapping_sync._constants import DESIGN_MODE_MANIFEST_FILENAME
from ii_agent.projects.design.source_mapping_sync._workspace import (
    _normalize_workspace_path,
    _read_file_with_workspace_fallback,
)


def _parse_design_mode_manifest_mapping(manifest_text: str) -> Dict[str, List[str]]:
    """
    Parse `design-mode.manifest.json` and return a mapping: design_id -> [file_path, ...].

    Supported formats:
    1) { "version": 1, "ids": { "<id>": "/workspace/.../file.tsx", ... } }
    2) { "version": 1, "elements": [ { "design_id": "<id>", "file_path": "/workspace/.../file.tsx" }, ... ] }
    3) { "<id>": "/workspace/.../file.tsx", ... } (legacy/simple mapping)
    """

    def _add(mapping: Dict[str, List[str]], design_id: Any, file_path: Any) -> None:
        if not isinstance(design_id, str) or not design_id.strip():
            return
        if not isinstance(file_path, str) or not file_path.strip():
            return
        normalized = _normalize_workspace_path(file_path)
        if not normalized:
            return
        paths = mapping.setdefault(design_id.strip(), [])
        if normalized not in paths:
            paths.append(normalized)

    if not isinstance(manifest_text, str) or not manifest_text.strip():
        return {}

    try:
        data = json.loads(manifest_text)
    except Exception:
        return {}

    mapping: Dict[str, List[str]] = {}

    if isinstance(data, dict):
        ids = data.get("ids")
        if isinstance(ids, dict):
            for design_id, file_path in ids.items():
                _add(mapping, design_id, file_path)
            return mapping

        elements = data.get("elements")
        if isinstance(elements, list):
            for el in elements:
                if not isinstance(el, dict):
                    continue
                design_id = el.get("design_id") or el.get("designId") or el.get("id")
                file_path = el.get("file_path") or el.get("filePath") or el.get("path")
                _add(mapping, design_id, file_path)
            return mapping

        # Accept a direct mapping { "<id>": "<path>" } if values are strings.
        for design_id, file_path in data.items():
            if isinstance(file_path, str):
                _add(mapping, design_id, file_path)
        return mapping

    return {}


async def _load_design_mode_manifest_mapping(
    sandbox: Any,
) -> tuple[Optional[str], Dict[str, List[str]]]:
    """
    Load and cache `design-mode.manifest.json` from the sandbox.

    Returns:
        (resolved_manifest_path, mapping)
    """
    cache_key = "design_mode_manifest_mapping"
    cached = getattr(sandbox, cache_key, None)
    if (
        isinstance(cached, tuple)
        and len(cached) == 2
        and (cached[0] is None or isinstance(cached[0], str))
        and isinstance(cached[1], dict)
    ):
        return cached[0], cached[1]

    default_path = f"/workspace/{DESIGN_MODE_MANIFEST_FILENAME}"
    try:
        manifest_text, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, default_path
        )
    except Exception:
        resolved_path = None
        manifest_text = ""

    mapping = _parse_design_mode_manifest_mapping(manifest_text)

    try:
        setattr(sandbox, cache_key, (resolved_path, mapping))
    except Exception:
        pass

    return resolved_path, mapping
