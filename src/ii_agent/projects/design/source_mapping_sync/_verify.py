"""Target matching/verification for source-mapping sync."""

from __future__ import annotations

import re
from typing import Optional

from ii_agent.projects.design.schemas import StyleChange
from ii_agent.projects.design.source_mapping_sync._backfill import (
    _extract_anchor_snippets,
    _split_class_tokens,
)
from ii_agent.projects.design.source_mapping_sync._tag_utils import (
    _extract_opening_tag_name,
    _find_opening_tag_bounds_for_design_id,
    _is_html_tag_name_for_design_mode,
    _normalize_whitespace_for_match,
)


def _extract_class_attr_from_outer_html(outer_html: object) -> Optional[str]:
    if not isinstance(outer_html, str) or not outer_html:
        return None
    match = re.search(
        r"(?<![\w-])class\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)",
        outer_html,
        re.DOTALL,
    )
    if not match:
        return None
    value = (match.group("val") or "").strip()
    return value or None


def _extract_literal_class_attr_from_tag(tag: str) -> Optional[str]:
    if not isinstance(tag, str) or not tag:
        return None
    for attr in ("className", "class"):
        match = re.search(
            rf"(?<![\w-]){attr}\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)",
            tag,
            re.DOTALL,
        )
        if match:
            value = (match.group("val") or "").strip()
            if value:
                return value
    return None


def _verify_design_mode_target_matches_context(
    *,
    change: StyleChange,
    content: str,
    file_path: str,
    design_id: str,
) -> tuple[bool, str]:
    """
    Best-effort guardrail to prevent applying a change to the wrong source element.

    We verify that the source tag we located via `data-design-id="..."` matches the
    element context captured in the iframe (tagName, nearby text anchors, class tokens).
    """
    ctx = change.elementContext
    if not ctx:
        return True, "no_context"

    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        return True, "tag_not_found"

    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    expected_tag = (getattr(ctx, "tagName", None) or "").strip().lower()
    source_tag = (_extract_opening_tag_name(tag) or "").strip()
    if expected_tag and source_tag:
        # Only enforce tag name match when the source tag is a real HTML tag.
        # In TSX/JSX, design IDs may live on React components (e.g. <Button ...>, <motion.h1 ...>),
        # which render to lowercase DOM tags at runtime.
        if (
            _is_html_tag_name_for_design_mode(source_tag)
            and source_tag.lower() != expected_tag
        ):
            return False, f"tag_name_mismatch expected={expected_tag} got={source_tag}"

    anchors = _extract_anchor_snippets(ctx)
    if anchors:
        window_start = max(0, tag_start - 4000)
        window_end = min(len(content), tag_end + 1 + 12000)
        window = _normalize_whitespace_for_match(content[window_start:window_end])
        found_anchor = False
        for anchor in anchors:
            normalized_anchor = _normalize_whitespace_for_match(anchor)
            if normalized_anchor and normalized_anchor in window:
                found_anchor = True
                break
        if not found_anchor:
            return False, "anchor_text_mismatch"

    expected_class_name = (getattr(ctx, "className", None) or "").strip()
    if not expected_class_name:
        expected_class_name = (
            _extract_class_attr_from_outer_html(getattr(ctx, "outerHTML", None)) or ""
        )

    expected_tokens = (
        _split_class_tokens(expected_class_name) if expected_class_name else []
    )
    source_class_literal = _extract_literal_class_attr_from_tag(tag)
    if expected_tokens and source_class_literal:
        source_tokens = set(_split_class_tokens(source_class_literal))
        overlap = len(set(expected_tokens) & source_tokens)

        # If we have anchors, class mismatch is not fatal (text already disambiguates).
        if not anchors:
            min_overlap = 1 if len(expected_tokens) <= 2 else 2
            if overlap < min_overlap:
                return (
                    False,
                    f"class_token_mismatch overlap={overlap} min={min_overlap}",
                )

    return True, "ok"
