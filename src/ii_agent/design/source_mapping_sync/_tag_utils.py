"""Tag/DOM parsing primitives for source-mapping sync."""

from __future__ import annotations

import re
from typing import Optional

from ii_agent.design.source_mapping_sync._constants import _DESIGN_MODE_HTML_TAG_NAMES


def _extract_opening_tag_name(tag: str) -> Optional[str]:
    if not isinstance(tag, str) or not tag:
        return None
    match = re.match(r"<\s*(?P<name>[A-Za-z][A-Za-z0-9:_.-]*)", tag)
    if not match:
        return None
    return (match.group("name") or "").strip() or None

def _extract_closing_tag_name(tag: str) -> Optional[str]:
    if not isinstance(tag, str) or not tag:
        return None
    match = re.match(r"</\s*(?P<name>[A-Za-z][A-Za-z0-9:_.-]*)", tag)
    if not match:
        return None
    return (match.group("name") or "").strip() or None

def _find_tag_end(text: str, start_index: int) -> Optional[int]:
    quote: Optional[str] = None
    brace_depth = 0
    i = start_index
    while i < len(text):
        ch = text[i]
        if quote is not None:
            if ch == quote and (i == 0 or text[i - 1] != "\\"):
                quote = None
        else:
            if ch in {"'", '"'}:
                quote = ch
            elif ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == ">" and brace_depth == 0:
                return i
        i += 1
    return None

def _is_html_tag_name_for_design_mode(value: str) -> bool:
    return (value or "").strip().lower() in _DESIGN_MODE_HTML_TAG_NAMES

def _tag_name_matches_for_design_mode(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a = a.strip()
    b = b.strip()
    if _is_html_tag_name_for_design_mode(a) and _is_html_tag_name_for_design_mode(b):
        return a.lower() == b.lower()
    return a == b

def _find_matching_closing_tag_end(
    content: str, start_index: int, tag_name: str
) -> Optional[int]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(tag_name, str) or not tag_name:
        return None

    depth = 1
    i = max(0, start_index)
    while i < len(content):
        lt = content.find("<", i)
        if lt == -1:
            return None

        if lt + 1 < len(content) and content[lt + 1] in {"!", "?"}:
            tag_end = _find_tag_end(content, lt)
            if tag_end is None:
                return None
            i = tag_end + 1
            continue

        tag_end = _find_tag_end(content, lt)
        if tag_end is None:
            return None

        tag = content[lt : tag_end + 1]
        is_closing = tag.startswith("</")
        is_self_closing = tag.rstrip().endswith("/>")

        if is_closing:
            name = _extract_closing_tag_name(tag)
            if name and _tag_name_matches_for_design_mode(name, tag_name):
                depth -= 1
                if depth == 0:
                    return tag_end
        else:
            name = _extract_opening_tag_name(tag)
            if name and _tag_name_matches_for_design_mode(name, tag_name):
                if not is_self_closing:
                    depth += 1

        i = tag_end + 1

    return None

def _find_opening_tag_bounds_for_design_id(
    content: str, design_id: str
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not isinstance(design_id, str) or not design_id:
        return None

    needles = [f'data-design-id="{design_id}"', f"data-design-id='{design_id}'"]
    match_index = -1
    for needle in needles:
        match_index = content.find(needle)
        if match_index != -1:
            break
    if match_index == -1:
        return None

    search_pos = match_index
    while True:
        tag_start = content.rfind("<", 0, search_pos + 1)
        if tag_start == -1:
            return None
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            search_pos = tag_start - 1
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None or match_index > tag_end:
            search_pos = tag_start - 1
            continue
        return tag_start, tag_end

def _find_element_span_for_design_id(
    content: str, design_id: str
) -> Optional[tuple[int, int]]:
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        return None
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    if tag.rstrip().endswith("/>"):
        return tag_start, tag_end + 1

    tag_name = _extract_opening_tag_name(tag)
    if not tag_name:
        return None

    closing_end = _find_matching_closing_tag_end(content, tag_end + 1, tag_name)
    if closing_end is None:
        return None

    return tag_start, closing_end + 1

def _normalize_whitespace_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()
