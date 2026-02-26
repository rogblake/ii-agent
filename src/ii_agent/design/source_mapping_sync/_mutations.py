"""Source-level mutation functions for source-mapping sync."""

from __future__ import annotations

import json
import posixpath
import re
import shlex
from typing import Any, Dict, List, Optional

from ii_agent.core.logger import logger
from ii_agent.design.source_mapping_sync._constants import (
    _DESIGN_MODE_CSS_OVERRIDES_END,
    _DESIGN_MODE_CSS_OVERRIDES_START,
    _truncate_for_log,
)
from ii_agent.design.source_mapping_sync._tag_utils import (
    _extract_opening_tag_name,
    _find_element_span_for_design_id,
    _find_matching_closing_tag_end,
    _find_opening_tag_bounds_for_design_id,
    _find_tag_end,
)
from ii_agent.design.source_mapping_sync._workspace import (
    _parse_search_paths,
    _read_file_with_workspace_fallback,
    _score_globals_css_candidate,
    _score_source_path,
    _search_workspace_for_fixed_string,
)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def _apply_delete_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
) -> tuple[str, bool]:
    """
    Delete an element identified by `design_id` from the source content.

    This removes the entire element including its opening tag, content, and closing tag.
    Leading whitespace on the same line is also removed to maintain clean formatting.
    """
    span = _find_element_span_for_design_id(content, design_id)
    if not span:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for delete designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    start, end = span

    # Try to also remove leading whitespace on the same line for cleaner formatting
    # Look backwards from start to find beginning of line
    line_start = start
    while line_start > 0 and content[line_start - 1] in " \t":
        line_start -= 1

    # If the line only contains whitespace before the element, include that whitespace in deletion
    if line_start == 0 or content[line_start - 1] == "\n":
        start = line_start

    # Also try to remove the trailing newline if the element was on its own line
    if end < len(content) and content[end] == "\n":
        end += 1

    updated = content[:start] + content[end:]

    logger.info(
        "[DesignMode Sync] (source-mapping) Deleted element designId=%s from %s (removed %d chars)",
        design_id,
        file_path,
        end - start,
    )

    return updated, True


# ---------------------------------------------------------------------------
# Icon helpers
# ---------------------------------------------------------------------------

def _normalize_lucide_icon_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    value = value.replace("_", "-").replace(" ", "-")
    value = re.sub(r"[^a-zA-Z0-9-]+", "", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value.lower()

def _lucide_icon_name_to_component_name(icon_name: str) -> Optional[str]:
    if not isinstance(icon_name, str):
        return None
    raw = icon_name.strip()
    if not raw:
        return None

    # Already a valid component identifier like "BrickWall" or "CheckCircle2".
    if re.fullmatch(r"[A-Z][A-Za-z0-9]*", raw):
        return raw

    normalized = _normalize_lucide_icon_name(raw)
    if not normalized:
        return None
    parts = [p for p in normalized.split("-") if p]
    if not parts:
        return None
    component = "".join(p[:1].upper() + p[1:] for p in parts)
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]*", component):
        return None
    return component

def _sanitize_svg_inner_for_jsx(svg_inner: str) -> str:
    """Convert common SVG dash-case attributes to JSX-compatible camelCase."""
    if not isinstance(svg_inner, str) or not svg_inner:
        return svg_inner

    raw = svg_inner.strip()

    # If a full `<svg>...</svg>` was provided, keep only its inner markup so we don't
    # nest `<svg>` elements when patching an existing SVG node.
    outer_svg_match = re.search(
        r"(?is)^\s*<svg\b[^>]*>(?P<inner>.*?)</svg\s*>\s*$", raw
    )
    if outer_svg_match:
        raw = (outer_svg_match.group("inner") or "").strip()
    elif re.match(r"(?is)^\s*<svg\b[^>]*/>\s*$", raw):
        # Self-closing wrapper: no inner content to apply.
        raw = ""
    elif raw.lower().startswith("<svg"):
        # Best-effort: strip an incomplete wrapper (e.g. truncated payloads).
        gt = raw.find(">")
        if gt != -1:
            raw = raw[gt + 1 :]
        raw = re.sub(r"(?is)</svg\s*>\s*$", "", raw).strip()

    replacements = {
        "stroke-width": "strokeWidth",
        "stroke-linecap": "strokeLinecap",
        "stroke-linejoin": "strokeLinejoin",
        "stroke-miterlimit": "strokeMiterlimit",
        "fill-rule": "fillRule",
        "clip-rule": "clipRule",
        "stop-color": "stopColor",
        "stop-opacity": "stopOpacity",
        "text-anchor": "textAnchor",
        "dominant-baseline": "dominantBaseline",
        "xlink:href": "xlinkHref",
        "xml:space": "xmlSpace",
    }

    out = raw
    for src, dst in replacements.items():
        out = re.sub(rf"(?<![\w-]){re.escape(src)}\s*=", f"{dst}=", out)
    return out

def _upsert_jsx_attribute_if_missing(tag: str, attr: str, value: str) -> str:
    """
    Best-effort helper to add `attr="value"` to a JSX opening tag string if missing.
    Does not attempt to handle dynamic JSX expressions.
    """
    if not isinstance(tag, str) or not tag:
        return tag
    if not isinstance(attr, str) or not attr.strip():
        return tag
    if re.search(rf"(?<![\w-]){re.escape(attr)}\s*=", tag):
        return tag
    insertion = f' {attr}="{value}"'
    if tag.rstrip().endswith("/>"):
        return re.sub(r"\s*/>\s*$", insertion + " />", tag, count=1)
    return re.sub(r">\s*$", insertion + ">", tag, count=1)

def _upsert_lucide_class_names_in_svg_opening_tag(
    tag: str, *, icon_name: Optional[str]
) -> str:
    """
    Best-effort: if `className="..."` is a string literal, append lucide marker classes so
    the resulting icon matches the runtime mutation behavior.
    """
    if not isinstance(tag, str) or not tag:
        return tag

    match = re.search(r"(?<![\w-])className\s*=\s*(['\"])(?P<cls>.*?)\1", tag)
    if not match:
        return tag

    quote = match.group(1)
    classes_raw = match.group("cls") or ""
    classes = [c for c in re.split(r"\s+", classes_raw.strip()) if c]

    wanted = ["lucide"]
    if isinstance(icon_name, str) and icon_name.strip():
        wanted.append(f"lucide-{icon_name.strip()}")

    added = False
    for w in wanted:
        if w not in classes:
            classes.append(w)
            added = True

    if not added:
        return tag

    new_attr = f'className={quote}{" ".join(classes)}{quote}'
    start, end = match.span()
    return tag[:start] + new_attr + tag[end:]


def _apply_icon_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
    icon_name: Optional[str],
    svg_inner: Optional[str],
) -> tuple[str, bool]:
    """
    Apply an icon change by locating the element with `data-design-id`.

    Supports:
    - Lucide React icon component replacement (<Zap /> -> <Bell />)
    - Inline SVG replacement (<svg>...</svg>) when `svg_inner` is provided
    """
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate tag for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    tag_name = _extract_opening_tag_name(tag)
    if not tag_name:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not extract tag name for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    # Case 1: Lucide React component replacement (<Zap /> -> <Bell />).
    if tag_name[:1].isupper():
        if not isinstance(icon_name, str) or not icon_name.strip():
            logger.warning(
                "[DesignMode Sync] (source-mapping) Missing icon name for designId=%s in %s",
                design_id,
                file_path,
            )
            return content, False

        old_icon_name = tag_name

        new_icon_component = _lucide_icon_name_to_component_name(icon_name)
        if not new_icon_component:
            logger.warning(
                "[DesignMode Sync] (source-mapping) Invalid lucide icon name %r for designId=%s in %s",
                icon_name,
                design_id,
                file_path,
            )
            return content, False

        # If already the same icon, treat as success
        if old_icon_name == new_icon_component:
            return content, True

        # Replace the icon in the opening tag
        updated_tag = re.sub(
            r"<\s*" + re.escape(old_icon_name) + r"\b",
            f"<{new_icon_component}",
            tag,
            count=1,
        )

        updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]

        # Check if this is a self-closing tag or has a closing tag
        if not tag.rstrip().endswith("/>"):
            # Find and replace the closing tag
            closing_tag_pattern = r"</\s*" + re.escape(old_icon_name) + r"\s*>"
            # Search in a reasonable window after the opening tag
            window_start = tag_start
            window_end = min(len(updated_content), window_start + 2000)
            window = updated_content[window_start:window_end]

            if re.search(closing_tag_pattern, window):
                window = re.sub(
                    closing_tag_pattern, f"</{new_icon_component}>", window, count=1
                )
                updated_content = (
                    updated_content[:window_start]
                    + window
                    + updated_content[window_end:]
                )

        # Update the lucide-react import line to include the new icon (and sanitize any invalid ones).
        import_pattern = r"import\s*\{\s*(?P<names>[^}]*)\s*\}\s*from\s*(?P<q>['\"])lucide-react(?P=q)\s*;?"
        import_match = re.search(import_pattern, updated_content)

        if import_match:
            names_raw = import_match.group("names") or ""
            quote = import_match.group("q") or "'"
            had_semicolon = import_match.group(0).rstrip().endswith(";")

            specifiers: list[str] = []
            seen: set[str] = set()
            for raw_spec in names_raw.split(","):
                spec = raw_spec.strip()
                if not spec:
                    continue

                imported_name = spec
                alias = None
                alias_parts = re.split(r"\s+as\s+", spec, maxsplit=1)
                if len(alias_parts) == 2:
                    imported_name = alias_parts[0].strip()
                    alias = alias_parts[1].strip() or None

                fixed_name = (
                    _lucide_icon_name_to_component_name(imported_name) or imported_name
                )
                spec_text = f"{fixed_name} as {alias}" if alias else fixed_name

                imported_symbol = fixed_name.strip()
                if imported_symbol and imported_symbol not in seen:
                    seen.add(imported_symbol)
                    specifiers.append(spec_text)

            if new_icon_component not in seen:
                specifiers.append(new_icon_component)
                seen.add(new_icon_component)

            content_without_import_line = (
                updated_content[: import_match.start()]
                + updated_content[import_match.end() :]
            )
            old_icon_usage_pattern = r"<" + re.escape(old_icon_name) + r"[\s/>]"
            if not re.search(old_icon_usage_pattern, content_without_import_line):
                specifiers = [
                    s
                    for s in specifiers
                    if re.split(r"\s+as\s+", s, maxsplit=1)[0].strip() != old_icon_name
                ]

            rebuilt_import = (
                f"import {{ {', '.join(specifiers)} }} from {quote}lucide-react{quote}"
            )
            if had_semicolon:
                rebuilt_import += ";"
            updated_content = (
                updated_content[: import_match.start()]
                + rebuilt_import
                + updated_content[import_match.end() :]
            )
        else:
            # No lucide-react import found, add one at the top after other imports
            # Find the last import statement
            last_import_match = None
            for match in re.finditer(
                r"import\s+.*?from\s+['\"].*?['\"];?\s*\n", updated_content
            ):
                last_import_match = match

            if last_import_match:
                insert_pos = last_import_match.end()
                new_import = f"import {{ {new_icon_component} }} from 'lucide-react'\n"
                updated_content = (
                    updated_content[:insert_pos]
                    + new_import
                    + updated_content[insert_pos:]
                )
            else:
                # No imports found, add at the beginning
                new_import = (
                    f"import {{ {new_icon_component} }} from 'lucide-react'\n\n"
                )
                updated_content = new_import + updated_content

        logger.info(
            "[DesignMode Sync] (source-mapping) Replaced icon %s -> %s for designId=%s in %s",
            old_icon_name,
            new_icon_component,
            design_id,
            file_path,
        )

        return updated_content, True

    # Case 2: Inline SVG replacement (<svg>...</svg>) when we have svg payload.
    if not isinstance(svg_inner, str) or not svg_inner.strip():
        logger.warning(
            "[DesignMode Sync] (source-mapping) Missing SVG payload for icon change designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    svg_inner = _sanitize_svg_inner_for_jsx(svg_inner.strip())
    if not svg_inner:
        logger.warning(
            "[DesignMode Sync] (source-mapping) SVG payload empty after sanitization for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    if tag_name.lower() == "svg":
        if tag.rstrip().endswith("/>"):
            # Convert to an explicit <svg>...</svg> block.
            opening = tag.rstrip()[:-2].rstrip() + ">"
            opening = _upsert_jsx_attribute_if_missing(opening, "viewBox", "0 0 24 24")
            opening = _upsert_jsx_attribute_if_missing(opening, "fill", "none")
            opening = _upsert_jsx_attribute_if_missing(
                opening, "stroke", "currentColor"
            )
            opening = _upsert_jsx_attribute_if_missing(opening, "strokeWidth", "2")
            opening = _upsert_jsx_attribute_if_missing(
                opening, "strokeLinecap", "round"
            )
            opening = _upsert_jsx_attribute_if_missing(
                opening, "strokeLinejoin", "round"
            )
            opening = _upsert_lucide_class_names_in_svg_opening_tag(
                opening, icon_name=icon_name
            )
            updated_content = (
                content[:tag_start]
                + opening
                + svg_inner
                + "</svg>"
                + content[tag_end + 1 :]
            )
            return updated_content, True

        closing_end = _find_matching_closing_tag_end(content, tag_end + 1, tag_name)
        if closing_end is None:
            return content, False
        closing_start = content.rfind("</", tag_end + 1, closing_end + 1)
        if closing_start == -1:
            return content, False

        opening = tag
        opening = _upsert_jsx_attribute_if_missing(opening, "viewBox", "0 0 24 24")
        opening = _upsert_jsx_attribute_if_missing(opening, "fill", "none")
        opening = _upsert_jsx_attribute_if_missing(opening, "stroke", "currentColor")
        opening = _upsert_jsx_attribute_if_missing(opening, "strokeWidth", "2")
        opening = _upsert_jsx_attribute_if_missing(opening, "strokeLinecap", "round")
        opening = _upsert_jsx_attribute_if_missing(opening, "strokeLinejoin", "round")
        opening = _upsert_lucide_class_names_in_svg_opening_tag(
            opening, icon_name=icon_name
        )

        updated_content = (
            content[:tag_start] + opening + svg_inner + content[closing_start:]
        )
        return updated_content, True

    # Fallback: designId may be on a wrapper; replace the first <svg> within the element span.
    span = _find_element_span_for_design_id(content, design_id)
    if not span:
        return content, False
    start, end = span
    fragment = content[start:end]
    svg_start = fragment.lower().find("<svg")
    if svg_start == -1:
        return content, False
    svg_open_end = _find_tag_end(fragment, svg_start)
    if svg_open_end is None:
        return content, False
    svg_open_tag = fragment[svg_start : svg_open_end + 1]
    svg_tag_name = _extract_opening_tag_name(svg_open_tag) or "svg"
    svg_close_end = _find_matching_closing_tag_end(
        fragment, svg_open_end + 1, svg_tag_name
    )
    if svg_close_end is None:
        return content, False
    svg_close_start = fragment.rfind("</", svg_open_end + 1, svg_close_end + 1)
    if svg_close_start == -1:
        return content, False

    updated_svg_open = svg_open_tag
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "viewBox", "0 0 24 24"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "fill", "none"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "stroke", "currentColor"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "strokeWidth", "2"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "strokeLinecap", "round"
    )
    updated_svg_open = _upsert_jsx_attribute_if_missing(
        updated_svg_open, "strokeLinejoin", "round"
    )
    updated_svg_open = _upsert_lucide_class_names_in_svg_opening_tag(
        updated_svg_open, icon_name=icon_name
    )

    updated_fragment = (
        fragment[:svg_start] + updated_svg_open + svg_inner + fragment[svg_close_start:]
    )
    updated_content = content[:start] + updated_fragment + content[end:]
    return updated_content, True


def _upsert_lucide_react_import_add_only(
    *, content: str, new_icon_component: str
) -> str:
    """
    Ensure `new_icon_component` is imported from `lucide-react`, without trying to remove
    other imports (some projects reference icons as identifiers, e.g. `icon: Shield`).
    """
    if not isinstance(content, str) or not content:
        return content
    if not isinstance(new_icon_component, str) or not new_icon_component.strip():
        return content
    new_icon_component = new_icon_component.strip()

    import_pattern = r"import\s*\{\s*(?P<names>[^}]*)\s*\}\s*from\s*(?P<q>['\"])lucide-react(?P=q)\s*;?"
    import_match = re.search(import_pattern, content)

    if import_match:
        names_raw = import_match.group("names") or ""
        quote = import_match.group("q") or "'"
        had_semicolon = import_match.group(0).rstrip().endswith(";")

        specifiers: list[str] = []
        seen: set[str] = set()
        for raw_spec in names_raw.split(","):
            spec = raw_spec.strip()
            if not spec:
                continue

            imported_name = spec
            alias = None
            alias_parts = re.split(r"\s+as\s+", spec, maxsplit=1)
            if len(alias_parts) == 2:
                imported_name = alias_parts[0].strip()
                alias = alias_parts[1].strip() or None

            fixed_name = (
                _lucide_icon_name_to_component_name(imported_name) or imported_name
            )
            spec_text = f"{fixed_name} as {alias}" if alias else fixed_name

            imported_symbol = fixed_name.strip()
            if imported_symbol and imported_symbol not in seen:
                seen.add(imported_symbol)
                specifiers.append(spec_text)

        if new_icon_component not in seen:
            specifiers.append(new_icon_component)

        rebuilt_import = (
            f"import {{ {', '.join(specifiers)} }} from {quote}lucide-react{quote}"
        )
        if had_semicolon:
            rebuilt_import += ";"
        return (
            content[: import_match.start()]
            + rebuilt_import
            + content[import_match.end() :]
        )

    # No lucide-react import found: add one at the top after other imports (if any).
    last_import_match = None
    for match in re.finditer(r"import\s+.*?from\s+['\"].*?['\"];?\s*\n", content):
        last_import_match = match

    if last_import_match:
        insert_pos = last_import_match.end()
        new_import = f"import {{ {new_icon_component} }} from 'lucide-react'\n"
        return content[:insert_pos] + new_import + content[insert_pos:]

    return f"import {{ {new_icon_component} }} from 'lucide-react'\n\n{content}"


def _apply_icon_change_by_item_id_assignment(
    *,
    content: str,
    file_path: str,
    item_id: str,
    icon_name: str,
) -> tuple[str, bool]:
    """
    Handle patterns like:
      const features = [{ id: "feature-1", icon: Shield }, ...]
      const features = [{ icon: Shield, id: "feature-1" }, ...]
      ...
      <feature.icon ... />
    by updating the object with `id == item_id` to `icon: <NewIconComponent>`.
    Handles both field orders (id before icon, or icon before id).
    """
    if not isinstance(content, str) or not content:
        return content, False
    if not isinstance(item_id, str) or not item_id.strip():
        return content, False
    item_id = item_id.strip()

    new_icon_component = _lucide_icon_name_to_component_name(icon_name)
    if not new_icon_component:
        return content, False

    # Try Pattern 1: id before icon (original pattern)
    # Match: { id: "1", ..., icon: Shield }
    pattern_id_first = re.compile(
        rf"(?s)(\{{[^{{}}]*?\bid\s*:\s*(?P<q>['\"])"
        rf"{re.escape(item_id)}(?P=q)[^{{}}]*?\bicon\s*:\s*)"
        rf"(?P<icon>[A-Za-z_$][A-Za-z0-9_$]*)"
    )
    match = pattern_id_first.search(content)

    # Try Pattern 2: icon before id
    # Match: { icon: Shield, ..., id: "1" }
    if not match:
        pattern_icon_first = re.compile(
            rf"(?s)(\{{[^{{}}]*?\bicon\s*:\s*)"
            rf"(?P<icon>[A-Za-z_$][A-Za-z0-9_$]*)"
            rf"([^{{}}]*?\bid\s*:\s*(?P<q>['\"])"
            rf"{re.escape(item_id)}(?P=q))"
        )
        match = pattern_icon_first.search(content)

    if not match:
        return content, False

    old_icon_component = match.group("icon") or ""
    if old_icon_component == new_icon_component:
        return content, True

    updated_content = (
        content[: match.start("icon")]
        + new_icon_component
        + content[match.end("icon") :]
    )
    updated_content = _upsert_lucide_react_import_add_only(
        content=updated_content, new_icon_component=new_icon_component
    )

    logger.info(
        "[DesignMode Sync] (source-mapping) Updated icon assignment %s -> %s for item_id=%s in %s",
        old_icon_component or "?",
        new_icon_component,
        item_id,
        file_path,
    )
    return updated_content, True


# ---------------------------------------------------------------------------
# Move / Swap
# ---------------------------------------------------------------------------

def _apply_move_change_by_design_ids(
    *,
    content: str,
    file_path: str,
    design_id: str,
    target_design_id: str,
    mode: str,
) -> tuple[str, bool]:
    """Move `design_id` element to be directly before/after `target_design_id`."""
    if design_id == target_design_id:
        return content, True
    if mode not in {"before", "after"}:
        return content, False

    span_a = _find_element_span_for_design_id(content, design_id)
    if not span_a:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    span_b = _find_element_span_for_design_id(content, target_design_id)
    if not span_b:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for target designId=%s in %s",
            target_design_id,
            file_path,
        )
        return content, False

    a_start, a_end = span_a
    b_start, b_end = span_b

    # Don't attempt to reorder nested/overlapping spans (not siblings in source).
    if not (a_end <= b_start or b_end <= a_start):
        logger.warning(
            "[DesignMode Sync] (source-mapping) Move spans overlap for designId=%s target=%s in %s",
            design_id,
            target_design_id,
            file_path,
        )
        return content, False

    a_block = content[a_start:a_end]
    removed = content[:a_start] + content[a_end:]

    # Re-find target span after removal so indices are correct.
    span_b2 = _find_element_span_for_design_id(removed, target_design_id)
    if not span_b2:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not re-locate target span for move designId=%s target=%s in %s",
            design_id,
            target_design_id,
            file_path,
        )
        return content, False

    insert_at = span_b2[0] if mode == "before" else span_b2[1]
    updated = removed[:insert_at] + a_block + removed[insert_at:]
    return updated, True


def _apply_move_change_by_design_id_anchor(
    *,
    content: str,
    file_path: str,
    design_id: str,
    anchor: str,
) -> tuple[str, bool]:
    """
    Move an element identified by `design_id` to a stable sibling anchor.

    Anchor format:
    - "before:<target-design-id>"
    - "after:<target-design-id>"
    - "only" (no-op)
    """
    if not isinstance(anchor, str) or not anchor:
        return content, False

    anchor = anchor.strip()
    if anchor == "only":
        # Treat as already-in-sync.
        return content, True

    mode: Optional[str] = None
    target_design_id: Optional[str] = None
    if anchor.startswith("before:"):
        mode = "before"
        target_design_id = anchor[len("before:"):].strip() or None
    elif anchor.startswith("after:"):
        mode = "after"
        target_design_id = anchor[len("after:"):].strip() or None

    if not mode or not target_design_id:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Unsupported move anchor for designId=%s in %s: %s",
            design_id,
            file_path,
            _truncate_for_log(anchor, limit=200),
        )
        return content, False

    return _apply_move_change_by_design_ids(
        content=content,
        file_path=file_path,
        design_id=design_id,
        target_design_id=target_design_id,
        mode=mode,
    )


def _apply_swap_change_by_design_ids(
    *,
    content: str,
    file_path: str,
    design_id: str,
    target_design_id: str,
) -> tuple[str, bool]:
    span_a = _find_element_span_for_design_id(content, design_id)
    if not span_a:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False

    span_b = _find_element_span_for_design_id(content, target_design_id)
    if not span_b:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate element span for target designId=%s in %s",
            target_design_id,
            file_path,
        )
        return content, False

    a_start, a_end = span_a
    b_start, b_end = span_b
    if a_start == b_start and a_end == b_end:
        return content, True

    if a_start > b_start:
        (a_start, a_end), (b_start, b_end) = (b_start, b_end), (a_start, a_end)
        design_id, target_design_id = target_design_id, design_id

    if a_end > b_start:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Swap spans overlap for designId=%s target=%s in %s",
            design_id,
            target_design_id,
            file_path,
        )
        return content, False

    a_block = content[a_start:a_end]
    b_block = content[b_start:b_end]
    updated = (
        content[:a_start] + b_block + content[a_end:b_start] + a_block + content[b_end:]
    )
    return updated, True


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def _apply_text_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
    old_text: str,
    new_text: str,
) -> tuple[str, bool]:
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        return content, False
    tag_start, tag_end = bounds

    if not old_text:
        return content, False

    window_start = tag_end + 1
    window_end = min(len(content), window_start + 6000)
    window = content[window_start:window_end]
    if old_text not in window:
        # Treat already-in-sync as success if the new text is present.
        if new_text and new_text in window:
            return content, True
        return content, False
    window = window.replace(old_text, new_text, 1)
    return content[:window_start] + window + content[window_end:], True


# ---------------------------------------------------------------------------
# Style (CSS overrides + inline)
# ---------------------------------------------------------------------------

async def _locate_project_globals_css(
    *, sandbox: Any, manifest_path: Optional[str]
) -> Optional[str]:
    cache_key = "design_mode_globals_css_paths"
    cached = getattr(sandbox, cache_key, None)
    if not isinstance(cached, dict):
        cached = {}
        try:
            setattr(sandbox, cache_key, cached)
        except Exception:
            cached = {}

    project_root = (
        posixpath.dirname(manifest_path)
        if isinstance(manifest_path, str) and manifest_path.startswith("/workspace/")
        else None
    )
    cache_bucket = project_root or "/workspace"
    cached_path = cached.get(cache_bucket)
    if isinstance(cached_path, str) and cached_path.startswith("/workspace/"):
        return cached_path

    search_root = project_root or "/workspace"
    find_cmd = (
        f"find {shlex.quote(search_root)} -type f -name globals.css "
        "-not -path '*/node_modules/*' "
        "-not -path '*/.git/*' "
        "-not -path '*/dist/*' "
        "-not -path '*/build/*' "
        "-not -path '*/.next/*' "
        "-print"
    )
    try:
        out = await sandbox.run_command(find_cmd)
    except Exception:
        out = ""
    candidates = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if not candidates and project_root:
        # Last resort: search across all of /workspace.
        try:
            out = await sandbox.run_command(find_cmd.replace(search_root, "/workspace", 1))
        except Exception:
            out = ""
        candidates = [line.strip() for line in (out or "").splitlines() if line.strip()]
    if not candidates:
        return None

    candidates.sort(key=lambda p: (_score_globals_css_candidate(p), len(p)))
    best = candidates[0]
    cached[cache_bucket] = best
    return best


def _escape_css_attribute_value(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _upsert_design_mode_css_override(
    *, css_text: str, design_id: str, css_prop: str, css_value: str
) -> str:
    if not isinstance(css_text, str):
        css_text = ""
    css_prop = (css_prop or "").strip()
    if not css_prop:
        return css_text

    selector = f'[data-design-id="{_escape_css_attribute_value(design_id)}"]'
    value = "" if css_value is None else str(css_value).strip()

    def _upsert_rule(section: str) -> str:
        pattern = re.compile(rf"(?s){re.escape(selector)}\s*\{{(?P<body>.*?)\}}\s*")
        match = pattern.search(section)

        if not match:
            if not value:
                return section
            block = f"{selector} {{\n  {css_prop}: {value};\n}}\n"
            section = section.rstrip() + ("\n\n" if section.strip() else "")
            return section + block

        body = match.group("body") or ""
        prop_line = re.compile(
            rf"(?m)^(?P<indent>\s*){re.escape(css_prop)}\s*:\s*[^;]*;\s*$"
        )

        if not value:
            new_body = prop_line.sub("", body)
        elif prop_line.search(body):
            new_body = prop_line.sub(rf"\g<indent>{css_prop}: {value};", body, count=1)
        else:
            indent_match = re.search(
                r"(?m)^(?P<indent>\s*)[A-Za-z_-][A-Za-z0-9_-]*\s*:", body
            )
            indent = indent_match.group("indent") if indent_match else "  "
            trimmed = body.rstrip("\n")
            if trimmed.strip():
                trimmed = trimmed + "\n"
            new_body = f"{trimmed}{indent}{css_prop}: {value};\n"

        # If no declarations remain, drop the whole block.
        if not re.search(r"(?m)^\s*[A-Za-z_-][A-Za-z0-9_-]*\s*:", new_body or ""):
            start, end = match.span()
            updated = section[:start] + section[end:]
            return updated.rstrip() + ("\n" if updated.strip() else "")

        rebuilt_block = f"{selector} {{\n{new_body.rstrip()}\n}}\n"
        start, end = match.span()
        return section[:start] + rebuilt_block + section[end:]

    start = css_text.find(_DESIGN_MODE_CSS_OVERRIDES_START)
    end = css_text.find(_DESIGN_MODE_CSS_OVERRIDES_END)
    has_section = start != -1 and end != -1 and end > start

    if not has_section:
        section = _upsert_rule("")
        rebuilt = css_text.rstrip()
        if rebuilt:
            rebuilt += "\n\n"
        rebuilt += (
            f"{_DESIGN_MODE_CSS_OVERRIDES_START}\n"
            f"{section.rstrip()}\n"
            f"{_DESIGN_MODE_CSS_OVERRIDES_END}\n"
        )
        return rebuilt

    section_start = start + len(_DESIGN_MODE_CSS_OVERRIDES_START)
    section_body = css_text[section_start:end].strip("\n")
    updated_section = _upsert_rule(section_body)
    return (
        css_text[:section_start]
        + "\n"
        + updated_section.strip("\n")
        + "\n"
        + css_text[end:]
    )


async def _apply_style_change_as_css_override(
    *,
    sandbox: Any,
    manifest_path: Optional[str],
    design_id: str,
    css_prop: str,
    css_value: str,
) -> tuple[bool, Optional[str]]:
    globals_css_path = await _locate_project_globals_css(
        sandbox=sandbox, manifest_path=manifest_path
    )
    if not globals_css_path:
        return False, None

    try:
        current_css = await sandbox.read_file(globals_css_path)
    except Exception:
        return False, None
    if not isinstance(current_css, str):
        try:
            current_css = str(current_css)
        except Exception:
            return False, None

    updated_css = _upsert_design_mode_css_override(
        css_text=current_css,
        design_id=design_id,
        css_prop=css_prop,
        css_value=css_value,
    )
    if updated_css == current_css:
        return True, globals_css_path

    try:
        await sandbox.write_file(globals_css_path, updated_css)
        ok = True
        return bool(ok), globals_css_path
    except Exception:
        return False, None


def _upsert_html_style_declaration(
    style_value: str, css_prop: str, css_value: str
) -> str:
    declarations: Dict[str, str] = {}
    order: List[str] = []

    for part in (style_value or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        key, val = part.split(":", 1)
        key = key.strip()
        if not key:
            continue
        if key not in declarations:
            order.append(key)
        declarations[key] = val.strip()

    css_prop = (css_prop or "").strip()
    if not css_prop:
        return style_value

    css_value = "" if css_value is None else str(css_value)

    if css_value == "":
        declarations.pop(css_prop, None)
        if css_prop in order:
            order = [k for k in order if k != css_prop]
    else:
        if css_prop not in declarations:
            order.append(css_prop)
        declarations[css_prop] = css_value

    if not order:
        return ""

    rebuilt = "; ".join(f"{k}: {declarations[k]}" for k in order if k in declarations)
    return rebuilt + ";"


def _upsert_html_style_attribute(
    tag: str, css_prop: str, css_value: str
) -> Optional[str]:
    if not isinstance(tag, str):
        return None
    match = re.search(
        r"(?<![\w-])style\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", tag, re.DOTALL
    )
    if not match:
        insert_at = None
        if tag.rstrip().endswith("/>"):
            insert_at = tag.rfind("/>")
        else:
            insert_at = tag.rfind(">")
        if insert_at is None or insert_at == -1:
            return None
        css_prop = (css_prop or "").strip()
        css_value = "" if css_value is None else str(css_value)
        if not css_prop or css_value == "":
            return tag
        insertion = f' style="{css_prop}: {css_value};"'
        return tag[:insert_at] + insertion + tag[insert_at:]

    existing = match.group("val")
    updated = _upsert_html_style_declaration(
        existing, css_prop, "" if css_value is None else str(css_value)
    )
    if updated == "":
        # Drop the style attribute entirely when no declarations remain.
        return tag[: match.start()] + tag[match.end() :]
    return tag[: match.start("val")] + updated + tag[match.end("val") :]


def _css_property_to_jsx_style_key(property_name: str) -> str:
    """Convert a CSS kebab-case property to a JSX style object key."""
    if not isinstance(property_name, str):
        return ""
    value = property_name.strip()
    if not value:
        return ""
    if value.startswith("--"):
        # Custom property: not directly supported as a JSX style key, but keep as-is.
        return value
    parts = [p for p in re.split(r"[-_]+", value) if p]
    if not parts:
        return value
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _escape_js_string_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _upsert_jsx_style_attribute(
    tag: str, css_prop: str, css_value: str
) -> Optional[str]:
    if not isinstance(tag, str):
        return None

    style_key = _css_property_to_jsx_style_key(css_prop)
    if not style_key:
        return None

    css_value = "" if css_value is None else str(css_value)
    if css_value == "":
        value_literal = "undefined"
    else:
        value_literal = f"'{_escape_js_string_literal(css_value)}'"

    def _extract_kv_pairs(expr: str) -> List[tuple[str, str]]:
        pairs: List[tuple[str, str]] = []
        if not isinstance(expr, str) or not expr:
            return pairs
        pattern = re.compile(
            r"\b(?P<key>[A-Za-z_$][A-Za-z0-9_$]*)\s*:\s*(?P<val>undefined|'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")"
        )
        for match in pattern.finditer(expr):
            key = match.group("key")
            val = match.group("val")
            if not key or not val:
                continue
            pairs.append((key, val))
        return pairs

    def _find_jsx_style_attr_ranges() -> List[tuple[int, int, str]]:
        """
        Return a list of (attr_start, attr_end, expression) for each `style={...}` in this tag.

        attr_start points to the `s` in `style`, and attr_end is the index *after* the closing `}`
        of the JSX expression.
        """
        ranges: List[tuple[int, int, str]] = []
        for match in re.finditer(r"(?<![\w-])style\s*=", tag):
            attr_start = match.start()
            eq_index = tag.find("=", match.end() - 1)
            if eq_index == -1:
                continue
            value_start = eq_index + 1
            while value_start < len(tag) and tag[value_start].isspace():
                value_start += 1
            if value_start >= len(tag) or tag[value_start] != "{":
                continue

            quote: Optional[str] = None
            depth = 0
            i = value_start
            while i < len(tag):
                ch = tag[i]
                if quote is not None:
                    if ch == quote and tag[i - 1] != "\\":
                        quote = None
                else:
                    if ch in {"'", '"'}:
                        quote = ch
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            break
                i += 1
            if depth != 0:
                continue

            value_end = i
            expression = tag[value_start + 1 : value_end].strip()
            ranges.append((attr_start, value_end + 1, expression))
        return ranges

    style_ranges = _find_jsx_style_attr_ranges()
    if not style_ranges:
        insert_at = None
        if tag.rstrip().endswith("/>"):
            insert_at = tag.rfind("/>")
        else:
            insert_at = tag.rfind(">")
        if insert_at is None or insert_at == -1:
            return None
        insertion = " style={{ " + style_key + ": " + value_literal + " }}"
        return tag[:insert_at] + insertion + tag[insert_at:]

    # Merge multiple `style={...}` attributes into one to avoid JSX prop overriding.
    spread_parts: List[str] = []
    kv_parts: List[str] = []

    for _start, _end, expr in style_ranges:
        if not isinstance(expr, str):
            continue
        trimmed = expr.strip()
        if not trimmed:
            continue

        # Normal/expected: object literal or expression.
        if trimmed.startswith("{") and trimmed.endswith("}"):
            spread_parts.append(f"...({trimmed})")
            continue

        # Repair corrupted expressions produced by earlier buggy syncs, e.g. when we accidentally wrote
        # `style={ ...({foo: 'bar'}), baz: 'qux' }` (missing the inner braces for an object literal).
        #
        # If an expression contains key/value pairs but isn't wrapped in `{...}`, extract the pairs
        # rather than attempting to spread an invalid expression containing `...`.
        if ":" in trimmed:
            extracted = _extract_kv_pairs(trimmed)
            if extracted:
                kv_parts.extend([f"{k}: {v}" for (k, v) in extracted])
                continue

        spread_parts.append(f"...({trimmed})")

    merged_inner = ", ".join(
        spread_parts + kv_parts + [f"{style_key}: {value_literal}"]
    )
    new_attr = f"style={{{{ {merged_inner} }}}}"

    # Remove all but the first style attribute.
    new_tag = tag
    for start, end, _expr in reversed(style_ranges[1:]):
        # Remove a preceding space if present to avoid leaving double spaces.
        if start > 0 and new_tag[start - 1].isspace():
            start -= 1
        new_tag = new_tag[:start] + new_tag[end:]

    first_start, first_end, _first_expr = style_ranges[0]
    return new_tag[:first_start] + new_attr + new_tag[first_end:]


def _apply_style_change_by_design_id(
    *,
    content: str,
    file_path: str,
    design_id: str,
    css_prop: str,
    css_value: str,
) -> tuple[str, bool]:
    bounds = _find_opening_tag_bounds_for_design_id(content, design_id)
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not locate tag for designId=%s in %s",
            design_id,
            file_path,
        )
        return content, False
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]

    ext = (posixpath.splitext(file_path or "")[1] or "").lower()
    is_html = ext in {".html", ".htm"}

    updated_tag: Optional[str]
    if is_html:
        updated_tag = _upsert_html_style_attribute(tag, css_prop, css_value)
    else:
        updated_tag = _upsert_jsx_style_attribute(tag, css_prop, css_value)

    if not updated_tag:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Could not update style for designId=%s css=%s in %s; tag=%s",
            design_id,
            css_prop,
            file_path,
            _truncate_for_log(tag, limit=400),
        )
        return content, False
    if updated_tag == tag:
        # Treat already-in-sync as success.
        return content, True
    return content[:tag_start] + updated_tag + content[tag_end + 1 :], True


# ---------------------------------------------------------------------------
# Icon extraction helpers (used by orchestrator)
# ---------------------------------------------------------------------------

def _extract_icon_payload_from_change(
    change: Any,
) -> tuple[Optional[str], Optional[str]]:
    """
    Icon changes are stored as change.type == "attribute" and change.property == "icon".

    The "to" value may be:
      - a dict like {"name":"brick-wall","svg":"..."}
      - a JSON string like {"name":"brick-wall","svg":"..."}
      - a plain string like "brick-wall"
      - raw SVG inner markup like "<path ... />"

    Returns:
      (icon_name, svg_inner), where each may be None.
    """
    if not change or not isinstance(getattr(change, "value", None), dict):
        return None, None

    to_value = change.value.get("to")
    if to_value is None:
        return None, None

    if isinstance(to_value, dict):
        name = to_value.get("name")
        svg = to_value.get("svg")
        icon_name = name.strip() if isinstance(name, str) and name.strip() else None
        svg_inner = svg.strip() if isinstance(svg, str) and svg.strip() else None
        return icon_name, svg_inner

    if not isinstance(to_value, str):
        return None, None

    raw = to_value.strip()
    if not raw:
        return None, None

    try:
        icon_data = json.loads(raw)
        if isinstance(icon_data, dict):
            name = icon_data.get("name")
            svg = icon_data.get("svg")
            icon_name = name.strip() if isinstance(name, str) and name.strip() else None
            svg_inner = svg.strip() if isinstance(svg, str) and svg.strip() else None
            return icon_name, svg_inner
    except Exception:
        pass

    # If it looks like SVG markup, treat it as svg_inner.
    if raw.startswith("<"):
        return None, raw

    return raw, None


def _extract_icon_name_from_change(change: Any) -> Optional[str]:
    icon_name, _svg_inner = _extract_icon_payload_from_change(change)
    return icon_name


def _extract_item_id_from_icon_design_id(design_id: str) -> Optional[str]:
    """
    DEPRECATED: Use _find_icon_by_dynamic_pattern instead for general solution.

    This function is kept for backwards compatibility with simple cases.
    """
    if not isinstance(design_id, str):
        return None
    value = design_id.strip()
    if not value:
        return None

    # Pattern 1: prefix-icon-suffix (e.g., "feature-icon-feature-1")
    if "-icon-" in value:
        parts = value.split("-icon-", 1)
        if len(parts) == 2:
            item_id = parts[1].strip()
            if item_id:
                return item_id

    # Pattern 2: prefix-{id}-icon (e.g., "features-card-1-icon")
    if value.endswith("-icon"):
        base = value[: -len("-icon")]
        segments = base.split("-")
        if segments:
            item_id = segments[-1].strip()
            if item_id:
                return item_id

    return None


# ---------------------------------------------------------------------------
# Source file finders (for icon changes)
# ---------------------------------------------------------------------------

async def _find_best_source_file_for_design_id(
    *, sandbox: Any, design_id: str
) -> Optional[str]:
    if not isinstance(design_id, str) or not design_id.strip():
        return None

    outputs: List[str] = []
    for needle in (f'data-design-id="{design_id}"', f"data-design-id='{design_id}'"):
        outputs.append(await _search_workspace_for_fixed_string(sandbox, needle))

    candidates: List[str] = []
    for out in outputs:
        candidates.extend(_parse_search_paths(out))

    if not candidates:
        logger.warning(
            "[DesignMode Sync] (source-mapping) No matches for data-design-id=%r in /workspace",
            design_id,
        )
        return None
    ranked = sorted(candidates, key=_score_source_path)
    best = ranked[0]
    logger.info(
        "[DesignMode Sync] (source-mapping) data-design-id=%r matched %d file(s); best=%s",
        design_id,
        len(ranked),
        best,
    )
    logger.debug(
        "[DesignMode Sync] (source-mapping) Candidate files for %r: %s",
        design_id,
        ", ".join(ranked[:10]) + (" ..." if len(ranked) > 10 else ""),
    )
    return best


async def _find_best_source_file_for_icon_item_id(
    *, sandbox: Any, item_id: str
) -> Optional[str]:
    if not isinstance(item_id, str) or not item_id.strip():
        return None
    item_id = item_id.strip()

    outputs: List[str] = []
    for needle in (f'"{item_id}"', f"'{item_id}'"):
        outputs.append(await _search_workspace_for_fixed_string(sandbox, needle))

    candidates: List[str] = []
    for out in outputs:
        candidates.extend(_parse_search_paths(out))
    if not candidates:
        return None

    ranked = sorted(candidates, key=_score_source_path)

    for path in ranked[:20]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content:
            continue

        # Check Pattern 1: id before icon
        check = re.search(
            rf"(?s)\{{[^{{}}]*?\bid\s*:\s*(['\"])"
            rf"{re.escape(item_id)}\1[^{{}}]*?\bicon\s*:\s*[A-Za-z_$][A-Za-z0-9_$]*",
            content,
        )
        # Check Pattern 2: icon before id
        if not check:
            check = re.search(
                rf"(?s)\{{[^{{}}]*?\bicon\s*:\s*[A-Za-z_$][A-Za-z0-9_$]*"
                rf"[^{{}}]*?\bid\s*:\s*(['\"]){re.escape(item_id)}\1",
                content,
            )
        if check:
            return resolved_path

    return None


# ---------------------------------------------------------------------------
# Dynamic icon pattern matching
# ---------------------------------------------------------------------------

def _update_icon_at_array_index(
    *,
    content: str,
    array_content: str,
    array_start: int,
    target_index: int,
    new_icon_component: str,
) -> str:
    """Update icon field in the Nth object in an array."""
    # Find all object literals in array
    objects = []
    depth = 0
    obj_start = -1

    for i, char in enumerate(array_content):
        if char == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                objects.append((obj_start, i + 1))
                obj_start = -1

    if target_index < 0 or target_index >= len(objects):
        return content

    obj_start, obj_end = objects[target_index]
    obj_content = array_content[obj_start:obj_end]

    # Find and replace icon field
    icon_pattern = re.compile(r"\bicon\s*:\s*([A-Z][A-Za-z0-9]*)")
    icon_match = icon_pattern.search(obj_content)

    if not icon_match:
        return content

    old_icon = icon_match.group(1)
    if old_icon == new_icon_component:
        return content

    # Replace in the actual content
    absolute_match_start = array_start + obj_start + icon_match.start(1)
    absolute_match_end = array_start + obj_start + icon_match.end(1)

    return (
        content[:absolute_match_start]
        + new_icon_component
        + content[absolute_match_end:]
    )


def _update_icon_where_field_matches(
    *,
    content: str,
    array_content: str,
    array_start: int,
    field_name: str,
    field_value: str,
    new_icon_component: str,
) -> str:
    """Update icon field in object where specified field matches value."""
    # Find objects in array and check each for matching field
    depth = 0
    obj_start = -1

    for i, char in enumerate(array_content):
        if char == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                obj_end = i + 1
                obj_content = array_content[obj_start:obj_end]

                # Check if this object has matching field value
                field_pattern = re.compile(
                    rf'\b{re.escape(field_name)}\s*:\s*["\']({re.escape(field_value)}|[\w-]+)["\']'
                )
                field_match = field_pattern.search(obj_content)

                if field_match and field_match.group(1) == field_value:
                    # Found the matching object! Update its icon
                    icon_pattern = re.compile(r"\bicon\s*:\s*([A-Z][A-Za-z0-9]*)")
                    icon_match = icon_pattern.search(obj_content)

                    if icon_match:
                        old_icon = icon_match.group(1)
                        if old_icon != new_icon_component:
                            absolute_match_start = (
                                array_start + obj_start + icon_match.start(1)
                            )
                            absolute_match_end = (
                                array_start + obj_start + icon_match.end(1)
                            )

                            return (
                                content[:absolute_match_start]
                                + new_icon_component
                                + content[absolute_match_end:]
                            )

                obj_start = -1

    return content


def _update_icon_in_array_by_value(
    *,
    content: str,
    array_start: int,
    target_value: str,
    variable_expr: str,
    iterator_var: str,
    index_var: Optional[str],
    new_icon_component: str,
) -> str:
    """
    Update icon in array element based on matching value.

    Handles:
    - Matching by field value: ${item.id} with target_value="1"
    - Matching by index: ${index} with target_value="0" or "1"
    """
    # Find the array in content starting from array_start
    # Parse array elements
    brace_count = 0
    array_content_start = -1
    array_content_end = -1

    for i in range(array_start, len(content)):
        if content[i] == "[":
            if array_content_start == -1:
                array_content_start = i + 1
            brace_count += 1
        elif content[i] == "]":
            brace_count -= 1
            if brace_count == 0:
                array_content_end = i
                break

    if array_content_start == -1 or array_content_end == -1:
        return content

    array_content = content[array_content_start:array_content_end]

    # If variable expression is just "index", match by position
    if variable_expr == index_var or variable_expr == "index":
        try:
            target_index = int(target_value)
            return _update_icon_at_array_index(
                content=content,
                array_content=array_content,
                array_start=array_content_start,
                target_index=target_index,
                new_icon_component=new_icon_component,
            )
        except (ValueError, TypeError):
            pass

    # Otherwise, match by field value
    # Extract field name from variable_expr (e.g., "feature.id" -> "id")
    field_match = re.match(rf"{re.escape(iterator_var)}\.(\w+)", variable_expr)
    if not field_match:
        return content

    field_name = field_match.group(1)

    # Find object in array with matching field value and update its icon
    return _update_icon_where_field_matches(
        content=content,
        array_content=array_content,
        array_start=array_content_start,
        field_name=field_name,
        field_value=target_value,
        new_icon_component=new_icon_component,
    )


def _apply_icon_change_by_dynamic_pattern(
    *, content: str, file_path: str, design_id: str, pattern: str, icon_name: str
) -> tuple[str, bool]:
    """
    Apply icon change by finding the array element at the inferred position.

    This handles cases where design IDs are generated like:
      data-design-id={`features-card-${feature.id}-icon`}
      data-design-id={`item-${index}-icon`}

    Strategy:
    1. Find where the pattern is used in a template string
    2. Extract the variable name being mapped (e.g., "feature", "item")
    3. Find the array being mapped over
    4. Determine the index from the design ID
    5. Update the icon field in that array element
    """
    if not content or not design_id or not pattern or not icon_name:
        return content, False

    new_icon_component = _lucide_icon_name_to_component_name(icon_name)
    if not new_icon_component:
        return content, False

    # Look for template strings that match our pattern
    # Example: data-design-id={`features-card-${feature.id}-icon`}
    template_pattern = re.compile(r"data-design-id=\{`([^`]*\$\{[^}]+\}[^`]*)`\}")

    matches = list(template_pattern.finditer(content))
    if not matches:
        return content, False

    # Try to find a match that could generate our design_id
    for match in matches:
        template = match.group(1)

        # Extract the static parts and variable parts
        # E.g., "features-card-${feature.id}-icon" -> ["features-card-", "feature.id", "-icon"]
        parts = re.split(r"\$\{([^}]+)\}", template)

        if len(parts) < 2:
            continue

        # Try to reconstruct the pattern to see if it matches our design_id
        # Replace ${...} with regex patterns
        test_pattern = re.escape(parts[0])
        for i in range(1, len(parts), 2):
            if i < len(parts):
                # Variable part - use flexible matching
                test_pattern += r"[\w-]+"
            if i + 1 < len(parts):
                # Static part
                test_pattern += re.escape(parts[i + 1])

        if not re.match(f"^{test_pattern}$", design_id):
            continue

        # This template could generate our design_id!
        # Now extract the variable expression (e.g., "feature.id", "index", "item.idx")
        variable_expr = parts[1] if len(parts) > 1 else None
        if not variable_expr:
            continue

        # Determine what value this variable should have for our design_id
        # Extract the actual value from design_id using the pattern
        value_pattern = re.escape(parts[0]) + r"([\w-]+)"
        if len(parts) > 2:
            value_pattern += re.escape(parts[2])

        value_match = re.match(value_pattern, design_id)
        if not value_match:
            continue

        target_value = value_match.group(1)

        # Find the context around this template string to locate the array
        # Look backwards for .map( or similar patterns
        context_start = max(0, match.start() - 1000)
        context = content[context_start : match.end() + 500]

        # Find array.map((item, index) => pattern
        map_pattern = re.compile(
            r"(\[[\s\S]*?\])\.map\s*\(\s*\(([^,)]+)(?:,\s*([^)]+))?\)\s*=>"
        )
        map_match = map_pattern.search(context)

        if not map_match:
            continue

        # Extract the iterator variable name (e.g., "feature", "item")
        iterator_var = map_match.group(2).strip()
        index_var = map_match.group(3).strip() if map_match.group(3) else None

        # Check if our variable expression uses this iterator
        if iterator_var not in variable_expr and (
            not index_var or index_var not in variable_expr
        ):
            continue

        # Find the array definition
        array_text = map_match.group(1)
        array_start_in_context = map_match.start(1)
        array_start = context_start + array_start_in_context

        # Try to find and update the icon in the array
        # Look for array elements with icon field
        updated = _update_icon_in_array_by_value(
            content=content,
            array_start=array_start,
            target_value=target_value,
            variable_expr=variable_expr,
            iterator_var=iterator_var,
            index_var=index_var,
            new_icon_component=new_icon_component,
        )

        if updated != content:
            # Update imports
            updated = _upsert_lucide_react_import_add_only(
                content=updated, new_icon_component=new_icon_component
            )
            logger.info(
                "[DesignMode Sync] (dynamic-pattern) Updated icon via pattern matching in %s",
                file_path,
            )
            return updated, True

    return content, False


def _infer_design_id_pattern(design_id: str) -> Optional[str]:
    """
    Convert a specific design ID to a regex pattern for finding similar IDs.

    Examples:
      features-card-1-icon -> features-card-\\d+-icon
      pricing-tier-pro-icon -> pricing-tier-\\w+-icon
      feature-icon-abc123 -> feature-icon-\\w+

    This helps find template-generated design IDs in source code.
    """
    if not isinstance(design_id, str) or not design_id.strip():
        return None

    # Replace sequences of digits with \d+
    # Replace sequences of word chars (letters/numbers) with \w+
    pattern = design_id

    # First, replace digit sequences
    pattern = re.sub(r"\d+", r"\\d+", pattern)

    # Then, replace word sequences that aren't already part of a \d+ replacement
    # Look for standalone alphanumeric segments (not already in regex form)
    parts = pattern.split("-")
    new_parts = []
    for part in parts:
        if part and not part.startswith("\\") and re.match(r"^[a-zA-Z]\w*$", part):
            # This is a word segment that might be dynamic
            # Keep common prefixes like "icon", "card", "item" as-is
            if part.lower() in (
                "icon",
                "card",
                "item",
                "feature",
                "features",
                "pricing",
                "tier",
            ):
                new_parts.append(part)
            else:
                # Replace with pattern for variable content
                new_parts.append(r"\w+")
        else:
            new_parts.append(part)

    pattern = "-".join(new_parts)
    return pattern


async def _find_icon_by_dynamic_pattern(
    *, sandbox: Any, design_id: str, icon_name: str, element_context: Any
) -> tuple[Optional[str], bool]:
    """
    General solution for finding and updating icons with dynamically generated design IDs.

    Strategy:
    1. Infer a pattern from the design ID (e.g., features-card-1-icon -> features-card-\\d+-icon)
    2. Search for this pattern in template strings in the codebase
    3. Find the JSX where this pattern is used
    4. Locate the data array being mapped
    5. Determine the position/index from the design ID
    6. Update the icon at that position in the array

    Args:
        sandbox: Sandbox instance
        design_id: The dynamic design ID (e.g., "features-card-1-icon")
        icon_name: The new icon name to apply
        element_context: Element context with metadata

    Returns:
        (updated_content, success) tuple, or (None, False) if not applicable
    """
    if not design_id or not icon_name:
        return None, False

    # Infer pattern from design ID
    pattern = _infer_design_id_pattern(design_id)
    if not pattern:
        return None, False

    logger.info(
        "[DesignMode Sync] (dynamic-pattern) Searching for pattern: %s (from designId=%s)",
        pattern,
        design_id,
    )

    # Search for files containing template string patterns that might match
    # Look for common template literal markers
    search_queries = [
        "`${",  # Template literal with interpolation
        "data-design-id={`",  # React template literal in JSX
    ]

    all_candidates = []
    for query in search_queries:
        output = await _search_workspace_for_fixed_string(sandbox, query)
        candidates = _parse_search_paths(output)
        all_candidates.extend(candidates)

    if not all_candidates:
        return None, False

    # Deduplicate and rank
    unique_candidates = list(dict.fromkeys(all_candidates))
    ranked = sorted(unique_candidates, key=_score_source_path)

    # Try to find and apply the change in each candidate file
    for candidate_path in ranked[:15]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, candidate_path
            )
        except Exception:
            continue

        if not isinstance(content, str) or not content:
            continue

        # Try to apply the change using pattern-based matching
        updated_content, success = _apply_icon_change_by_dynamic_pattern(
            content=content,
            file_path=resolved_path,
            design_id=design_id,
            pattern=pattern,
            icon_name=icon_name,
        )

        if success:
            # Write the updated content
            try:
                await sandbox.write_file(resolved_path, updated_content)
                ok = True
                if ok:
                    logger.info(
                        "[DesignMode Sync] (dynamic-pattern) Successfully applied icon change in %s",
                        resolved_path,
                    )
                    return updated_content, True
            except Exception as exc:
                logger.warning(
                    "[DesignMode Sync] (dynamic-pattern) Failed to write %s: %s",
                    resolved_path,
                    exc,
                )
                continue

    return None, False
