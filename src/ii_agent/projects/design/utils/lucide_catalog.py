"""Lucide icon catalog helpers for Design Mode tool handlers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

_ICON_NODE_RE = re.compile(
    r"(?:const|var)\s+__iconNode\s*=\s*(\[[\s\S]*?\]);", re.MULTILINE
)


def _normalize_icon_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    value = value.replace("_", "-").replace(" ", "-")
    value = re.sub(r"[^a-zA-Z0-9-]+", "", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value.lower()


def _repo_root() -> Path:
    # src/ii_agent/projects/design/utils/lucide_catalog.py -> repo root
    return Path(__file__).resolve().parents[5]


@lru_cache(maxsize=1)
def _catalog_paths() -> list[Path]:
    root = _repo_root()
    return [
        Path(__file__).with_name("lucide_icons.json"),
        root / "lucide_icons.json",
    ]


@lru_cache(maxsize=1)
def _load_catalog() -> Dict[str, str]:
    for catalog_path in _catalog_paths():
        if not catalog_path.exists():
            continue
        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        out: Dict[str, str] = {}
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            normalized = _normalize_icon_name(key)
            if normalized:
                out[normalized] = value
        if out:
            return out
    return {}


@lru_cache(maxsize=1)
def _resolve_icons_dir() -> Optional[Path]:
    root = _repo_root()
    candidates = [
        root / "frontend" / "node_modules" / "lucide-react" / "dist" / "esm" / "icons",
        root / "node_modules" / "lucide-react" / "dist" / "esm" / "icons",
    ]
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate
        except Exception:
            continue
    return None


@lru_cache(maxsize=1)
def _list_available_icon_names() -> List[str]:
    names: set[str] = set(_load_catalog().keys())
    icons_dir = _resolve_icons_dir()
    if icons_dir and icons_dir.is_dir():
        try:
            for icon_file in icons_dir.glob("*.js"):
                if icon_file.name.endswith(".map"):
                    continue
                normalized = _normalize_icon_name(icon_file.stem)
                if normalized:
                    names.add(normalized)
        except Exception:
            pass
    return sorted(names)


def _camel_to_kebab(value: str) -> str:
    if not value:
        return value
    return re.sub(r"(?<!^)([A-Z])", r"-\1", value).lower()


def _parse_icon_node_from_file(icon_path: Path) -> Optional[List]:
    try:
        content = icon_path.read_text(encoding="utf-8")
    except Exception:
        return None

    match = _ICON_NODE_RE.search(content)
    if not match:
        return None

    array_literal = match.group(1)
    jsonish = re.sub(
        r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:",
        r'\1"\2":',
        array_literal,
    )
    jsonish = re.sub(r",\s*([}\]])", r"\1", jsonish)

    try:
        parsed = json.loads(jsonish)
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    return parsed


def _icon_node_to_svg_inner(icon_node: List) -> Optional[str]:
    parts: List[str] = []
    for entry in icon_node:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not isinstance(entry[1], dict)
        ):
            continue
        tag = entry[0].strip()
        if not tag or not re.match(r"^[a-zA-Z][\w:-]*$", tag):
            continue
        attrs: Dict[str, str] = {}
        for key, value in entry[1].items():
            if key == "key" or not isinstance(key, str) or value is None:
                continue
            value_str = str(value) if not isinstance(value, str) else value
            escaped = (
                value_str.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            attrs[_camel_to_kebab(key)] = escaped
        attr_str = "".join(f' {k}="{v}"' for k, v in attrs.items())
        parts.append(f"<{tag}{attr_str} />")
    if not parts:
        return None
    return "".join(parts)


@lru_cache(maxsize=256)
def _load_icon_svg_inner_from_esm_dir(normalized_name: str) -> Optional[str]:
    icons_dir = _resolve_icons_dir()
    if not icons_dir:
        return None
    icon_path = icons_dir / f"{normalized_name}.js"
    if not icon_path.exists():
        return None
    icon_node = _parse_icon_node_from_file(icon_path)
    if not icon_node:
        return None
    return _icon_node_to_svg_inner(icon_node)


def list_icons(query: str | None = None, limit: int = 50) -> List[str]:
    icons = _list_available_icon_names()
    if not icons:
        return []
    normalized_query = _normalize_icon_name(query or "")
    bounded_limit = max(1, min(limit, 250))
    if not normalized_query:
        return icons[:bounded_limit]
    matches = [name for name in icons if normalized_query in name]
    return matches[:bounded_limit]


def get_icon_svg_inner(name: str) -> Optional[str]:
    catalog = _load_catalog()
    key = _normalize_icon_name(name)
    if not key:
        return None
    if catalog:
        svg = catalog.get(key)
        if isinstance(svg, str) and svg:
            return svg
    return _load_icon_svg_inner_from_esm_dir(key)


__all__ = [
    "list_icons",
    "get_icon_svg_inner",
]
