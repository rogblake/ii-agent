"""Deterministic source-mapping sync pipeline for Design Mode."""

from __future__ import annotations

import bisect
import json
import posixpath
import re
import shlex
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urlparse

from ii_agent.core.logger import logger
from ii_agent.design.schemas import ElementContext, StyleChange


# Constants copied from the deterministic sync implementation.
DESIGN_MODE_MANIFEST_FILENAME = "design-mode.manifest.json"
_DESIGN_MODE_CSS_OVERRIDES_START = "/* === Design Mode Overrides (ii-agent) === */"
_DESIGN_MODE_CSS_OVERRIDES_END = "/* === End Design Mode Overrides === */"
_DESIGN_MODE_HTML_TAG_NAMES: set[str] = {
    "a", "abbr", "address", "area", "article", "aside", "audio", "b", "base", "bdi", "bdo",
    "blockquote", "body", "br", "button", "canvas", "caption", "cite", "code", "col", "colgroup",
    "data", "datalist", "dd", "del", "details", "dfn", "dialog", "div", "dl", "dt", "em",
    "embed", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5",
    "h6", "head", "header", "hgroup", "hr", "html", "i", "iframe", "img", "input", "ins", "kbd",
    "label", "legend", "li", "link", "main", "map", "mark", "menu", "meta", "meter", "nav", "noscript",
    "object", "ol", "optgroup", "option", "output", "p", "param", "picture", "pre", "progress", "q",
    "rp", "rt", "ruby", "s", "samp", "script", "section", "select", "small", "source", "span", "strong",
    "style", "sub", "summary", "sup", "svg", "table", "tbody", "td", "template", "textarea", "tfoot",
    "th", "thead", "time", "title", "tr", "track", "u", "ul", "var", "video", "wbr", "path", "g", "circle",
    "rect", "line", "polyline", "polygon", "ellipse", "text", "defs", "clipPath", "mask", "linearGradient",
    "radialGradient", "stop", "use", "symbol",
}


def _normalize_workspace_path(file_path: str) -> Optional[str]:
    return _normalize_workspace_file_path(file_path)


async def _emit_sync_progress(
    *,
    emit_progress: Optional[Callable[..., Awaitable[None]]],
    session_id: Optional[uuid.UUID],
    processed: int,
    total: int,
    applied: int,
    errors: int,
    current: Optional[int] = None,
    done: bool = False,
) -> None:
    if emit_progress is None:
        return
    await emit_progress(
        session_id=session_id,
        processed=processed,
        total=total,
        applied=applied,
        errors=errors,
        current=current,
        done=done,
    )

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

def _truncate_for_log(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"

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
        target_design_id = anchor[len("before:") :].strip() or None
    elif anchor.startswith("after:"):
        mode = "after"
        target_design_id = anchor[len("after:") :].strip() or None

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

def _score_globals_css_candidate(path: str) -> int:
    lowered = (path or "").lower()
    if lowered.endswith("/src/app/globals.css"):
        return 0
    if lowered.endswith("/app/globals.css"):
        return 1
    if lowered.endswith("/src/styles/globals.css"):
        return 2
    if lowered.endswith("/styles/globals.css"):
        return 3
    return 9

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

def _extract_anchor_snippets(ctx: Optional[ElementContext]) -> List[str]:
    if not ctx:
        return []

    def _split_anchor_candidates(value: str) -> List[str]:
        """
        Turn iframe-captured text (often `innerText`) into source-searchable anchors.

        Important: container elements' `innerText` concatenates descendant texts that are separated
        by tags in source, so we must split into smaller, atomic snippets (lines/sentences).
        """
        if not isinstance(value, str):
            return []
        text = value.strip()
        if not text or text.lower() == "n/a":
            return []

        parts: List[str] = [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]
        if not parts:
            parts = [text]

        # If it's still a single long run, also split by sentence-ish boundaries so we can match
        # contiguous substrings that likely exist as literals in source.
        if len(parts) == 1 and len(parts[0]) > 80:
            sentence_parts = [
                p.strip()
                for p in re.split(r"(?<=[.!?])\s+", parts[0])
                if p and p.strip()
            ]
            if len(sentence_parts) > 1:
                parts = sentence_parts

        return parts

    raw_candidates: List[str] = []
    for value in (
        ctx.textContent,
        ctx.nextSiblingText,
        ctx.prevSiblingText,
        ctx.contextText,
    ):
        for part in _split_anchor_candidates(value):
            raw_candidates.append(part[:120])
            if len(raw_candidates) >= 8:
                break
        if len(raw_candidates) >= 8:
            break

    deduped: List[str] = []
    seen: set[str] = set()
    for snippet in raw_candidates:
        if snippet in seen:
            continue
        seen.add(snippet)
        deduped.append(snippet)
    return deduped

def _find_best_opening_tag_by_class_tokens(
    *,
    content: str,
    class_name: str,
    class_tokens: List[str],
    preferred_tag_name: Optional[str],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(class_name, str) or not class_name.strip():
        return None
    if not isinstance(class_tokens, list) or not class_tokens:
        return None

    normalized_class = " ".join(class_name.split())
    preferred = (preferred_tag_name or "").strip().lower() or None

    best: Optional[tuple[tuple[int, int, int, int, int], int, int]] = None
    for m in re.finditer(r"<[A-Za-z][A-Za-z0-9:_-]*", content):
        tag_start = m.start()
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        tag = content[tag_start : tag_end + 1]

        if "className" not in tag and "class" not in tag:
            continue

        full_match = 1 if normalized_class and normalized_class in tag else 0
        token_matches = 0
        for token in class_tokens:
            if token and token in tag:
                token_matches += 1

        if full_match == 0 and token_matches < (1 if len(class_tokens) == 1 else 2):
            continue

        tag_name_match = 0
        if preferred:
            name_match = re.match(r"<\s*(?P<name>[A-Za-z][A-Za-z0-9:_-]*)", tag)
            if name_match and (name_match.group("name") or "").lower() == preferred:
                tag_name_match = 1

        # Prefer elements that do NOT already have a data-design-id; we don't want to steal IDs.
        has_existing_id = 1 if "data-design-id" in tag else 0

        score = (
            -full_match,
            -token_matches,
            has_existing_id,
            -tag_name_match,
            tag_start,
        )
        if best is None or score < best[0]:
            best = (score, tag_start, tag_end)

    if not best:
        return None
    return best[1], best[2]

def _parse_search_paths(output: str) -> List[str]:
    paths: List[str] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(?P<path>/[^:]+):(?P<line>\d+):", line)
        if not match:
            continue
        path = match.group("path").strip()
        if not path:
            continue
        paths.append(path)
    # De-dupe while preserving order.
    deduped: List[str] = []
    seen: set[str] = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)
    return deduped

async def _get_workspace_top_level_dirs(sandbox: Any) -> List[str]:
    """
    List top-level directories directly under `/workspace` (cached per sandbox object).

    These are used both for prompting (so the model can return absolute paths) and
    for resolving workspace-relative paths.
    """
    cache_key = "design_mode_workspace_roots"
    cached = getattr(sandbox, cache_key, None)
    if isinstance(cached, list) and all(isinstance(item, str) for item in cached):
        return cached

    roots: List[str] = []
    try:
        roots_out = await sandbox.run_command(
            "find /workspace -maxdepth 1 -mindepth 1 -type d -print"
        )
        roots = [
            line.strip() for line in (roots_out or "").splitlines() if line.strip()
        ]
    except Exception:
        roots = []

    ignored_basenames = {
        ".git",
        "node_modules",
        "__pycache__",
        ".cache",
        ".next",
        "dist",
        "build",
    }
    filtered: List[str] = []
    for root in roots:
        base = posixpath.basename(root.rstrip("/"))
        if base in ignored_basenames:
            continue
        if not root.startswith("/workspace/"):
            continue
        filtered.append(root)

    filtered.sort()
    try:
        setattr(sandbox, cache_key, filtered)
    except Exception:
        pass
    return filtered

def _workspace_relative_path(normalized_workspace_path: str) -> Optional[str]:
    if not isinstance(normalized_workspace_path, str):
        return None
    path = normalized_workspace_path.strip()
    if not path.startswith("/workspace/"):
        return None
    rel = path[len("/workspace/") :]
    if not rel or rel.startswith("/"):
        return None
    rel = posixpath.normpath(rel)
    if rel.startswith("../") or rel == "..":
        return None
    return rel

async def _read_file_with_workspace_fallback(
    sandbox: Any, normalized_workspace_path: str
) -> tuple[str, str]:
    """
    Read a file from the sandbox, with fallbacks for projects nested under `/workspace/<project>/...`.

    Returns:
        (content, resolved_path)
    """
    last_error: Optional[Exception] = None

    def _coerce_text(content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, (bytes, bytearray)):
            try:
                return bytes(content).decode("utf-8")
            except Exception:
                return None
        return None

    # 1) Direct read.
    try:
        content = await sandbox.read_file(normalized_workspace_path)
        text = _coerce_text(content)
        if text is not None:
            return text, normalized_workspace_path
    except Exception as exc:
        last_error = exc

    relative_path = _workspace_relative_path(normalized_workspace_path)
    if not relative_path:
        if last_error:
            raise last_error
        raise FileNotFoundError(normalized_workspace_path)

    # 2) Try `/workspace/*/<relative_path>` for each top-level directory.
    for root in await _get_workspace_top_level_dirs(sandbox):
        candidate = posixpath.normpath(posixpath.join(root, relative_path))
        if not candidate.startswith("/workspace/"):
            continue
        try:
            content = await sandbox.read_file(candidate)
            text = _coerce_text(content)
            if text is not None:
                return text, candidate
        except Exception as exc:
            last_error = exc

    # 3) Fallback: `find` by suffix anywhere in /workspace (excluding heavy dirs).
    try:
        pattern = f"*/{relative_path}"
        find_cmd = (
            "find /workspace -type f "
            "-not -path '*/node_modules/*' "
            "-not -path '*/.git/*' "
            "-not -path '*/dist/*' "
            "-not -path '*/build/*' "
            "-not -path '*/.next/*' "
            f"-path {shlex.quote(pattern)} "
            "-print -quit"
        )
        found = (await sandbox.run_command(find_cmd) or "").strip()
        if found:
            content = await sandbox.read_file(found)
            text = _coerce_text(content)
            if text is not None:
                return text, found
    except Exception as exc:
        last_error = exc

    if last_error:
        raise last_error
    raise FileNotFoundError(normalized_workspace_path)

def _score_source_path(path: str) -> tuple[int, int, int]:
    lowered = (path or "").lower()
    ext_rank = 9
    for ext, rank in (
        (".tsx", 0),
        (".jsx", 1),
        (".ts", 2),
        (".js", 3),
        (".html", 4),
        (".css", 5),
        (".vue", 6),
        (".svelte", 7),
    ):
        if lowered.endswith(ext):
            ext_rank = rank
            break
    in_src = 0 if "/src/" in lowered else 1
    return (ext_rank, in_src, len(path))

async def _search_workspace_for_fixed_string(sandbox: Any, query: str) -> str:
    quoted = shlex.quote(query)
    cmd = (
        "if command -v rg >/dev/null 2>&1; then "
        f"rg --no-heading -n -F --hidden "
        "--glob '!**/node_modules/**' "
        "--glob '!**/.git/**' "
        "--glob '!**/dist/**' "
        "--glob '!**/build/**' "
        "--glob '!**/.next/**' "
        f"{quoted} /workspace | head -n 50; "
        "else "
        "grep -R -n -F "
        "--exclude-dir=node_modules "
        "--exclude-dir=.git "
        "--exclude-dir=dist "
        "--exclude-dir=build "
        "--exclude-dir=.next "
        f"-e {quoted} /workspace | head -n 50; "
        "fi"
    )
    try:
        return await sandbox.run_command(cmd) or ""
    except Exception:
        return ""

def _split_class_tokens(class_name: str) -> List[str]:
    if not isinstance(class_name, str):
        return []
    tokens = [t.strip() for t in re.split(r"\s+", class_name.strip()) if t.strip()]
    deduped: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped

def _class_token_distinctiveness(token: str) -> int:
    if not isinstance(token, str):
        return 0
    score = len(token)
    if any(ch in token for ch in "/[]():#%"):
        score += 25
    if any(ch.isdigit() for ch in token):
        score += 6
    if token.startswith("data-") or token.startswith("aria-"):
        score += 12
    return score

def _upsert_data_design_id_attribute(tag: str, design_id: str) -> Optional[str]:
    if not isinstance(tag, str) or not isinstance(design_id, str) or not design_id:
        return None

    # If a design id already exists, only treat it as a match when it is the same id.
    # If it is a different id, do NOT overwrite (we likely matched the wrong element).
    existing_match = re.search(
        r"\bdata-design-id\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", tag
    )
    if existing_match:
        existing_val = (existing_match.group("val") or "").strip()
        if existing_val == design_id:
            return tag
        return None
    if "data-design-id" in tag:
        # Unknown/unsupported form like data-design-id={...}; do not overwrite.
        return None

    insert_at = None
    if tag.rstrip().endswith("/>"):
        insert_at = tag.rfind("/>")
    else:
        insert_at = tag.rfind(">")
    if insert_at is None or insert_at == -1:
        return None
    insertion = f' data-design-id="{design_id}"'
    return tag[:insert_at] + insertion + tag[insert_at:]

async def _backfill_design_id_in_source_from_class_name(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx:
        return None

    class_name = None
    if isinstance(ctx.className, str) and ctx.className.strip():
        class_name = " ".join(ctx.className.split())
    elif isinstance(ctx.outerHTML, str) and ctx.outerHTML:
        match = re.search(
            r"\bclass\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", ctx.outerHTML
        )
        if match and match.group("val").strip():
            class_name = " ".join(match.group("val").strip().split())

    if not class_name:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill (className) skipped: missing className/outerHTML for designId=%s",
            design_id,
        )
        return None

    class_tokens = _split_class_tokens(class_name)
    if not class_tokens:
        return None

    anchors = _extract_anchor_snippets(ctx)

    search_out = await _search_workspace_for_fixed_string(sandbox, class_name)
    candidates = _parse_search_paths(search_out)
    if candidates:
        ranked = sorted(candidates, key=_score_source_path)
        best_path = ranked[0]
        logger.info(
            "[DesignMode Sync] (source-mapping) Backfill (className) exact match: designId=%s files=%d best=%s",
            design_id,
            len(ranked),
            best_path,
        )
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, best_path
            )
        except Exception:
            content = None
            resolved_path = None

        if (
            isinstance(content, str)
            and content
            and isinstance(resolved_path, str)
            and resolved_path
        ):
            bounds = _find_best_opening_tag_by_class_tokens(
                content=content,
                class_name=class_name,
                class_tokens=class_tokens,
                preferred_tag_name=ctx.tagName,
            )
            if bounds:
                tag_start, tag_end = bounds
                tag = content[tag_start : tag_end + 1]
                updated_tag = _upsert_data_design_id_attribute(tag, design_id)
                if updated_tag and updated_tag != tag:
                    return (
                        resolved_path,
                        content[:tag_start] + updated_tag + content[tag_end + 1 :],
                    )
                if updated_tag == tag:
                    return resolved_path, content

    ranked_tokens = sorted(class_tokens, key=_class_token_distinctiveness, reverse=True)
    tokens_to_search = ranked_tokens[: min(8, len(ranked_tokens))]

    file_hits: Dict[str, int] = {}
    for token in tokens_to_search:
        out = await _search_workspace_for_fixed_string(sandbox, token)
        for path in _parse_search_paths(out):
            file_hits[path] = file_hits.get(path, 0) + 1

    if not file_hits:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill (className) failed: no token matches in /workspace for designId=%s",
            design_id,
        )
        return None

    ranked_files = sorted(
        file_hits.items(),
        key=lambda kv: (-kv[1], _score_source_path(kv[0])),
    )

    best_content: Optional[str] = None
    best_path: Optional[str] = None
    best_anchor_hits = -1
    best_token_hits = -1

    for path, token_hit_count in ranked_files[:5]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content:
            continue

        anchor_hits = 0
        for anchor in anchors:
            if anchor and anchor in content:
                anchor_hits += 1

        if (
            anchor_hits > best_anchor_hits
            or (anchor_hits == best_anchor_hits and token_hit_count > best_token_hits)
            or (
                anchor_hits == best_anchor_hits
                and token_hit_count == best_token_hits
                and best_path
                and _score_source_path(resolved_path) < _score_source_path(best_path)
            )
        ):
            best_content = content
            best_path = resolved_path
            best_anchor_hits = anchor_hits
            best_token_hits = token_hit_count

    if not best_content or not best_path:
        return None

    logger.info(
        "[DesignMode Sync] (source-mapping) Backfill (className) candidate: designId=%s file=%s tokens=%d anchors=%d",
        design_id,
        best_path,
        best_token_hits,
        best_anchor_hits,
    )

    bounds = _find_best_opening_tag_by_class_tokens(
        content=best_content,
        class_name=class_name,
        class_tokens=class_tokens,
        preferred_tag_name=ctx.tagName,
    )
    if not bounds:
        return None
    tag_start, tag_end = bounds
    tag = best_content[tag_start : tag_end + 1]
    updated_tag = _upsert_data_design_id_attribute(tag, design_id)
    if not updated_tag:
        return None
    if updated_tag == tag:
        return best_path, best_content
    return (
        best_path,
        best_content[:tag_start] + updated_tag + best_content[tag_end + 1 :],
    )

def _normalize_whitespace_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()

def _find_best_component_callsite_opening_tag(
    *,
    content: str,
    component_name: str,
    anchors: List[str],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(component_name, str) or not component_name:
        return None

    normalized_anchors = [
        _normalize_whitespace_for_match(a) for a in anchors if isinstance(a, str) and a
    ]
    normalized_anchors = [a for a in normalized_anchors if a]
    if not normalized_anchors:
        return None

    # Match `<Component ...` with a word-ish boundary afterwards.
    pattern = re.compile(r"<\s*" + re.escape(component_name) + r"(?![A-Za-z0-9:_.-])")

    best: Optional[tuple[int, int, int]] = None  # (-anchor_hits, has_id, tag_start)
    best_bounds: Optional[tuple[int, int]] = None

    for match in pattern.finditer(content):
        tag_start = match.start()
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        tag = content[tag_start : tag_end + 1]

        span_start = tag_start
        span_end = tag_end + 1
        if not tag.rstrip().endswith("/>"):
            closing_end = _find_matching_closing_tag_end(
                content, tag_end + 1, component_name
            )
            if closing_end is None:
                continue
            span_end = closing_end + 1

        window = _normalize_whitespace_for_match(content[span_start:span_end])
        anchor_hits = 0
        for anchor in normalized_anchors:
            if anchor in window:
                anchor_hits += 1

        if anchor_hits <= 0:
            continue

        has_existing_id = 1 if "data-design-id" in tag else 0
        score = (-anchor_hits, has_existing_id, tag_start)
        if best is None or score < best:
            best = score
            best_bounds = (tag_start, tag_end)

    return best_bounds

def _infer_component_name_before_index(content: str, index: int) -> Optional[str]:
    """
    Best-effort: infer the nearest React component name defined above `index`.

    This is used when a runtime element's className is defined inside a reusable component
    (e.g., shadcn/ui `CardHeader`), but the callsite doesn't include the className literal.
    """
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(index, int) or index <= 0:
        return None

    window_start = max(0, index - 3000)
    window = content[window_start:index]

    patterns = (
        r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*React\.forwardRef",
        r"(?:export\s+)?const\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*forwardRef",
        r"(?:export\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
    )

    candidates: List[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, window):
            name = (match.group("name") or "").strip()
            if not name:
                continue
            candidates.append((match.start(), name))

    if not candidates:
        return None
    # Choose the nearest definition above index.
    return max(candidates, key=lambda t: t[0])[1]

async def _backfill_design_id_in_source_from_component_callsite(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    """
    Backfill `data-design-id` into a React component callsite when the runtime element's className
    comes from a reusable component definition (so the className literal isn't present at the callsite).

    Example: `CardHeader` renders a `<div className="flex flex-col ...">` internally. We infer the
    component name from the className definition file, then locate the correct callsite by anchor text.
    """
    ctx = change.elementContext
    if not ctx:
        return None

    class_name = None
    if isinstance(ctx.className, str) and ctx.className.strip():
        class_name = " ".join(ctx.className.split())
    elif isinstance(ctx.outerHTML, str) and ctx.outerHTML:
        match = re.search(
            r"\bclass\s*=\s*(?P<q>['\"])(?P<val>.*?)(?P=q)", ctx.outerHTML
        )
        if match and match.group("val").strip():
            class_name = " ".join(match.group("val").strip().split())

    anchors = _extract_anchor_snippets(ctx)
    if not class_name or not anchors:
        return None

    # 1) Find definition files that contain the className literal.
    search_out = await _search_workspace_for_fixed_string(sandbox, class_name)
    definition_paths = sorted(_parse_search_paths(search_out), key=_score_source_path)
    if not definition_paths:
        return None

    component_names: List[str] = []
    for def_path in definition_paths[:5]:
        try:
            definition_content, _resolved_def_path = (
                await _read_file_with_workspace_fallback(sandbox, def_path)
            )
        except Exception:
            continue
        if not isinstance(definition_content, str) or not definition_content:
            continue

        for match in re.finditer(re.escape(class_name), definition_content):
            inferred = _infer_component_name_before_index(
                definition_content, match.start()
            )
            if inferred and inferred not in component_names:
                component_names.append(inferred)
        if component_names:
            break

    if not component_names:
        return None

    # 2) Use anchor snippets to find the callsite file (where text literals exist).
    anchor_queries = sorted(anchors, key=lambda s: (-len(s or ""), s or ""))[:3]
    callsite_candidates: List[str] = []
    for anchor in anchor_queries:
        out = await _search_workspace_for_fixed_string(sandbox, anchor)
        callsite_candidates.extend(_parse_search_paths(out))

    # De-dupe while preserving order, then rank.
    deduped: List[str] = []
    seen: set[str] = set()
    for p in callsite_candidates:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    ranked_callsite_paths = sorted(deduped, key=_score_source_path)
    for path in ranked_callsite_paths[:8]:
        try:
            content, resolved_path = await _read_file_with_workspace_fallback(
                sandbox, path
            )
        except Exception:
            continue
        if not isinstance(content, str) or not content or not resolved_path:
            continue

        for component_name in component_names:
            if f"<{component_name}" not in content:
                continue
            bounds = _find_best_component_callsite_opening_tag(
                content=content, component_name=component_name, anchors=anchor_queries
            )
            if not bounds:
                continue
            tag_start, tag_end = bounds
            tag = content[tag_start : tag_end + 1]
            updated_tag = _upsert_data_design_id_attribute(tag, design_id)
            if not updated_tag:
                continue
            if updated_tag == tag:
                return resolved_path, content
            updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
            logger.info(
                "[DesignMode Sync] (source-mapping) Backfill (callsite) inferred component=%s file=%s designId=%s",
                component_name,
                resolved_path,
                design_id,
            )
            return resolved_path, updated_content

    return None

def _build_line_start_offsets(content: str) -> List[int]:
    offsets = [0]
    if not isinstance(content, str) or not content:
        return offsets
    for i, ch in enumerate(content):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets

def _pos_to_line_number(line_start_offsets: List[int], pos: int) -> int:
    # line numbers are 1-based
    if not line_start_offsets:
        return 1
    return bisect.bisect_right(line_start_offsets, pos)

def _find_best_opening_tag_near_source_location(
    *,
    content: str,
    line_no: int,
    column_no: Optional[int],
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(line_no, int) or line_no <= 0:
        return None

    line_offsets = _build_line_start_offsets(content)
    if line_no > len(line_offsets):
        return None

    base_pos = line_offsets[line_no - 1]
    if isinstance(column_no, int) and column_no > 0:
        base_pos = min(len(content) - 1, base_pos + (column_no - 1))

    window_chars = 8000
    window_start = max(0, base_pos - window_chars)
    window_end = min(len(content), base_pos + window_chars)
    window = content[window_start:window_end]

    best: Optional[tuple[int, int, int]] = None  # (score, tag_start, tag_end)
    for m in re.finditer(r"<[A-Za-z][A-Za-z0-9:_-]*", window):
        tag_start = window_start + m.start()
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None:
            continue
        cand_line = _pos_to_line_number(line_offsets, tag_start)
        line_dist = abs(cand_line - line_no)
        pos_dist = abs(tag_start - base_pos)
        score = line_dist * 100_000 + pos_dist
        if best is None or score < best[0]:
            best = (score, tag_start, tag_end)

    if not best:
        return None
    return best[1], best[2]

def _normalize_react_source_file_name(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None

    value = value.split("#", 1)[0].split("?", 1)[0]

    # Handle fileName values that look like URLs.
    if "://" in value:
        try:
            value = urlparse(value).path or value
        except Exception:
            pass

    value = value.replace("\\", "/")

    # Handle webpack style: webpack:///./src/App.tsx
    if value.startswith("webpack://"):
        value = value[len("webpack://") :]

    value = value.lstrip("/")
    if value.startswith("./"):
        value = value[2:]

    # If the path is absolute but not under /workspace, salvage a src-relative suffix.
    # This commonly happens when devtools report an absolute host path.
    if (
        value.startswith("Users/")
        or value.startswith("home/")
        or value.startswith("var/")
    ):
        match = re.search(r"(?P<suffix>src/.*)$", value)
        if match:
            value = match.group("suffix")
        else:
            return None

    if not value:
        return None
    return value

def _normalize_workspace_file_path(file_path: str) -> Optional[str]:
    """
    Normalize a potentially workspace-relative path into an absolute sandbox path.

    Design Mode sync is expected to only modify files under `/workspace`.
    """
    if not isinstance(file_path, str):
        return None

    path = file_path.strip()
    if not path:
        return None

    # Strip trivial wrappers from LLMs.
    if len(path) >= 2 and path[0] == path[-1] and path[0] in {"`", '"', "'"}:
        path = path[1:-1].strip()

    path = path.replace("\\", "/")
    if path.startswith("file://"):
        path = path[len("file://") :]
    if path.startswith("workspace/"):
        path = f"/{path}"
    elif path == "workspace":
        path = "/workspace"

    if not path:
        return None

    if path.startswith("/workspace/"):
        normalized = posixpath.normpath(path)
    elif path.startswith("/"):
        # Keep Design Mode sync safely scoped to workspace.
        logger.warning(
            "[DesignMode Sync] Rejecting non-workspace absolute path: %s", path
        )
        return None
    else:
        normalized = posixpath.normpath(posixpath.join("/workspace", path))

    if normalized == "/workspace":
        logger.warning("[DesignMode Sync] Rejecting workspace root path: %s", file_path)
        return None

    if not normalized.startswith("/workspace/"):
        logger.warning(
            "[DesignMode Sync] Rejecting path escaping workspace: %s -> %s",
            file_path,
            normalized,
        )
        return None

    return normalized

async def _backfill_design_id_in_source_from_react_source(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx or not isinstance(ctx.reactSource, dict):
        return None

    raw_file = ctx.reactSource.get("fileName")
    normalized_file = _normalize_react_source_file_name(raw_file)
    if not normalized_file:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: missing/invalid reactSource.fileName=%r for designId=%s",
            raw_file,
            design_id,
        )
        return None

    normalized_path = _normalize_workspace_file_path(normalized_file)
    if not normalized_path:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: could not normalize reactSource file path %r for designId=%s",
            normalized_file,
            design_id,
        )
        return None

    line_no = None
    try:
        line_no = int(ctx.reactSource.get("lineNumber") or 0) or None
    except Exception:
        line_no = None
    if not line_no:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: missing reactSource.lineNumber for designId=%s",
            design_id,
        )
        return None

    column_no = None
    try:
        column_no = int(ctx.reactSource.get("columnNumber") or 0) or None
    except Exception:
        column_no = None

    try:
        content, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, normalized_path
        )
    except Exception:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Backfill failed: could not read reactSource file %s (from %r) for designId=%s",
            normalized_path,
            raw_file,
            design_id,
        )
        return None

    if not isinstance(content, str) or not content:
        return None

    bounds = _find_best_opening_tag_near_source_location(
        content=content, line_no=line_no, column_no=column_no
    )
    if not bounds:
        logger.warning(
            "[DesignMode Sync] (source-mapping) Backfill failed: could not locate JSX tag near %s:%s for designId=%s",
            resolved_path,
            line_no,
            design_id,
        )
        return None
    tag_start, tag_end = bounds
    tag = content[tag_start : tag_end + 1]
    updated_tag = _upsert_data_design_id_attribute(tag, design_id)
    if not updated_tag:
        return None
    if updated_tag == tag:
        return resolved_path, content
    updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
    return resolved_path, updated_content

async def _backfill_design_id_in_source_from_text_search(
    *,
    sandbox: Any,
    change: StyleChange,
    design_id: str,
) -> Optional[tuple[str, str]]:
    ctx = change.elementContext
    if not ctx or not isinstance(ctx.textContent, str):
        return None
    text = ctx.textContent.strip()
    if not text or text.upper() == "N/A":
        return None

    query = text[:80]
    search_out = await _search_workspace_for_fixed_string(sandbox, query)
    candidates = _parse_search_paths(search_out)
    if not candidates:
        logger.debug(
            "[DesignMode Sync] (source-mapping) Backfill skipped: text query not found in /workspace for designId=%s",
            design_id,
        )
        return None
    best_path = sorted(candidates, key=_score_source_path)[0]

    try:
        content, resolved_path = await _read_file_with_workspace_fallback(
            sandbox, best_path
        )
    except Exception:
        return None

    if not isinstance(content, str) or not content:
        return None

    idx = content.find(query)
    if idx == -1:
        return None

    search_pos = idx
    while True:
        tag_start = content.rfind("<", 0, search_pos + 1)
        if tag_start == -1:
            return None
        if tag_start + 1 < len(content) and content[tag_start + 1] in {"/", "!", "?"}:
            search_pos = tag_start - 1
            continue
        tag_end = _find_tag_end(content, tag_start)
        if tag_end is None or tag_end >= idx:
            search_pos = tag_start - 1
            continue
        tag = content[tag_start : tag_end + 1]
        updated_tag = _upsert_data_design_id_attribute(tag, design_id)
        if not updated_tag:
            return None
        if updated_tag == tag:
            return resolved_path, content
        updated_content = content[:tag_start] + updated_tag + content[tag_end + 1 :]
        return resolved_path, updated_content

async def _emit_design_mode_sync_progress(
    *,
    emit_progress: Optional[Callable[..., Awaitable[None]]],
    session_id: Optional[uuid.UUID],
    processed: int,
    total: int,
    applied: int,
    errors: int,
    current: Optional[int] = None,
    done: bool = False,
) -> None:
    await _emit_sync_progress(
        emit_progress=emit_progress,
        session_id=session_id,
        processed=processed,
        total=total,
        applied=applied,
        errors=errors,
        current=current,
        done=done,
    )

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

def _extract_class_attr_from_outer_html(outer_html: Any) -> Optional[str]:
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

async def _apply_changes_with_source_mapping(
    *,
    sandbox: Any,
    changes: List[StyleChange],
    session_id: Optional[uuid.UUID] = None,
    emit_progress: Optional[Callable[..., Awaitable[None]]] = None,
) -> tuple[int, List[str], List[StyleChange]]:
    """
    Apply Design Mode changes deterministically by locating `data-design-id="..."` in source files.

    This avoids spending LLM tokens on file/component searching. It expects Design Mode IDs to exist
    in the sandbox source (e.g., injected at project generation time).
    """
    applied_count = 0
    errors: List[str] = []
    remaining: List[StyleChange] = []

    logger.info(
        "[DesignMode Sync] (source-mapping) Applying %d change(s) using data-design-id mapping",
        len(changes),
    )

    manifest_path: Optional[str]
    manifest_mapping: Dict[str, List[str]]
    try:
        manifest_path, manifest_mapping = await _load_design_mode_manifest_mapping(
            sandbox
        )
    except Exception:
        manifest_path, manifest_mapping = None, {}

    if manifest_mapping:
        logger.info(
            "[DesignMode Sync] (source-mapping) Loaded %d Design Mode manifest entries from %s",
            len(manifest_mapping),
            manifest_path or f"/workspace/{DESIGN_MODE_MANIFEST_FILENAME}",
        )
    else:
        logger.info(
            "[DesignMode Sync] (source-mapping) No Design Mode manifest loaded; using workspace search/backfill"
        )

    await _emit_design_mode_sync_progress(
        emit_progress=emit_progress,
        session_id=session_id,
        processed=0,
        total=len(changes),
        applied=0,
        errors=0,
        current=1 if changes else None,
        done=False,
    )
    for idx, change in enumerate(changes, start=1):
        await _emit_design_mode_sync_progress(
            emit_progress=emit_progress,
            session_id=session_id,
            processed=idx - 1,
            total=len(changes),
            applied=applied_count,
            errors=len(errors),
            current=idx,
            done=False,
        )
        ctx = change.elementContext
        design_id = None
        if ctx and isinstance(ctx.designId, str) and ctx.designId.strip():
            design_id = ctx.designId.strip()
        elif isinstance(change.designId, str) and change.designId.strip():
            design_id = change.designId.strip()

        if not design_id:
            remaining.append(change)
            errors.append(f"Change {idx}: Missing designId")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d missing designId",
                idx,
                len(changes),
            )
            continue

        try:
            to_preview = None
            if isinstance(change.value, dict):
                to_preview = change.value.get("to")
            logger.info(
                "[DesignMode Sync] (source-mapping) Change %d/%d: designId=%s type=%s property=%s to=%s",
                idx,
                len(changes),
                design_id,
                change.type,
                change.property,
                (
                    _truncate_for_log(str(to_preview), limit=200)
                    if to_preview is not None
                    else "None"
                ),
            )
        except Exception:
            pass

        file_path: Optional[str] = None
        manifest_used = False
        if manifest_mapping:
            manifest_paths = manifest_mapping.get(design_id) or []
            if len(manifest_paths) == 1:
                file_path = manifest_paths[0]
                manifest_used = True
            else:
                if not manifest_paths:
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: designId=%s missing from %s; falling back to workspace search",
                        idx,
                        len(changes),
                        design_id,
                        DESIGN_MODE_MANIFEST_FILENAME,
                    )
                else:
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: manifest mapping ambiguous for designId=%s: %s; falling back to workspace search",
                        idx,
                        len(changes),
                        design_id,
                        manifest_paths,
                    )
                file_path = await _find_best_source_file_for_design_id(
                    sandbox=sandbox, design_id=design_id
                )
        else:
            file_path = await _find_best_source_file_for_design_id(
                sandbox=sandbox, design_id=design_id
            )
        content: Optional[str] = None
        resolved_path: Optional[str] = None

        if file_path:
            try:
                content, resolved_path = await _read_file_with_workspace_fallback(
                    sandbox, file_path
                )
            except Exception as exc:
                remaining.append(change)
                errors.append(f"Change {idx}: Failed to read {file_path}: {exc}")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d: failed to read %s: %s",
                    idx,
                    len(changes),
                    file_path,
                    exc,
                )
                continue
            if manifest_used and isinstance(content, str):
                if (
                    f'data-design-id="{design_id}"' not in content
                    and f"data-design-id='{design_id}'" not in content
                ):
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Manifest drift: designId=%s not found in %s; falling back to workspace search",
                        design_id,
                        resolved_path,
                    )
                    searched = await _find_best_source_file_for_design_id(
                        sandbox=sandbox, design_id=design_id
                    )
                    if searched:
                        try:
                            content, resolved_path = (
                                await _read_file_with_workspace_fallback(
                                    sandbox, searched
                                )
                            )
                        except Exception:
                            pass
        else:
            if change.type == "attribute" and change.property == "icon":
                icon_name = _extract_icon_name_from_change(change)
                item_id = _extract_item_id_from_icon_design_id(design_id)
                if icon_name and item_id:
                    candidate_path = await _find_best_source_file_for_icon_item_id(
                        sandbox=sandbox, item_id=item_id
                    )
                    if candidate_path:
                        try:
                            cand_content, cand_resolved_path = (
                                await _read_file_with_workspace_fallback(
                                    sandbox, candidate_path
                                )
                            )
                        except Exception:
                            cand_content = None
                            cand_resolved_path = None

                        if (
                            isinstance(cand_content, str)
                            and cand_content
                            and isinstance(cand_resolved_path, str)
                            and cand_resolved_path
                        ):
                            updated_candidate, applied_candidate = (
                                _apply_icon_change_by_item_id_assignment(
                                    content=cand_content,
                                    file_path=cand_resolved_path,
                                    item_id=item_id,
                                    icon_name=icon_name,
                                )
                            )
                            if applied_candidate:
                                try:
                                    await sandbox.write_file(
                                        cand_resolved_path, updated_candidate
                                    )
                                    ok = True
                                except Exception as exc:
                                    ok = False
                                    errors.append(
                                        f"Change {idx}: Failed to write {cand_resolved_path}: {exc}"
                                    )
                                if ok:
                                    applied_count += 1
                                    logger.info(
                                        "[DesignMode Sync] (source-mapping) Change %d/%d applied via icon assignment fallback in %s",
                                        idx,
                                        len(changes),
                                        cand_resolved_path,
                                    )
                                    continue

            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d: data-design-id=%s not found in source; attempting backfill",
                idx,
                len(changes),
                design_id,
            )
            backfilled = await _backfill_design_id_in_source_from_react_source(
                sandbox=sandbox,
                change=change,
                design_id=design_id,
            )
            if backfilled:
                candidate_path, candidate_content = backfilled
                ok, reason = _verify_design_mode_target_matches_context(
                    change=change,
                    content=candidate_content,
                    file_path=candidate_path,
                    design_id=design_id,
                )
                if not ok:
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting reactSource backfill candidate for designId=%s (%s)",
                        idx,
                        len(changes),
                        design_id,
                        reason,
                    )
                    backfilled = None
            if not backfilled:
                backfilled = await _backfill_design_id_in_source_from_text_search(
                    sandbox=sandbox,
                    change=change,
                    design_id=design_id,
                )
                if backfilled:
                    candidate_path, candidate_content = backfilled
                    ok, reason = _verify_design_mode_target_matches_context(
                        change=change,
                        content=candidate_content,
                        file_path=candidate_path,
                        design_id=design_id,
                    )
                    if not ok:
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting text-search backfill candidate for designId=%s (%s)",
                            idx,
                            len(changes),
                            design_id,
                            reason,
                        )
                        backfilled = None
            if not backfilled:
                backfilled = await _backfill_design_id_in_source_from_class_name(
                    sandbox=sandbox,
                    change=change,
                    design_id=design_id,
                )
                if backfilled:
                    candidate_path, candidate_content = backfilled
                    ok, reason = _verify_design_mode_target_matches_context(
                        change=change,
                        content=candidate_content,
                        file_path=candidate_path,
                        design_id=design_id,
                    )
                    if not ok:
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting className backfill candidate for designId=%s (%s)",
                            idx,
                            len(changes),
                            design_id,
                            reason,
                        )
                        backfilled = None
            if not backfilled:
                backfilled = (
                    await _backfill_design_id_in_source_from_component_callsite(
                        sandbox=sandbox,
                        change=change,
                        design_id=design_id,
                    )
                )
                if backfilled:
                    candidate_path, candidate_content = backfilled
                    ok, reason = _verify_design_mode_target_matches_context(
                        change=change,
                        content=candidate_content,
                        file_path=candidate_path,
                        design_id=design_id,
                    )
                    if not ok:
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: rejecting callsite backfill candidate for designId=%s (%s)",
                            idx,
                            len(changes),
                            design_id,
                            reason,
                        )
                        backfilled = None
            if not backfilled:
                # Try dynamic pattern matching for icon changes (general solution)
                if change.type == "attribute" and change.property == "icon":
                    icon_name = _extract_icon_name_from_change(change)
                    if icon_name:
                        logger.info(
                            "[DesignMode Sync] (source-mapping) Change %d/%d: attempting dynamic pattern matching for icon designId=%s",
                            idx,
                            len(changes),
                            design_id,
                        )
                        dynamic_content, dynamic_success = (
                            await _find_icon_by_dynamic_pattern(
                                sandbox=sandbox,
                                design_id=design_id,
                                icon_name=icon_name,
                                element_context=change.elementContext,
                            )
                        )
                        if dynamic_success:
                            applied_count += 1
                            logger.info(
                                "[DesignMode Sync] (source-mapping) Change %d/%d applied via dynamic pattern matching",
                                idx,
                                len(changes),
                            )
                            continue

            if not backfilled:
                if change.type == "style":
                    to_value = None
                    if isinstance(change.value, dict):
                        to_value = change.value.get("to")
                    if to_value is not None:
                        css_ok, css_path = await _apply_style_change_as_css_override(
                            sandbox=sandbox,
                            manifest_path=manifest_path,
                            design_id=design_id,
                            css_prop=str(change.property or ""),
                            css_value="" if to_value is None else str(to_value),
                        )
                        if css_ok:
                            applied_count += 1
                            logger.info(
                                "[DesignMode Sync] (source-mapping) Change %d/%d applied as CSS override in %s",
                                idx,
                                len(changes),
                                css_path,
                            )
                            continue

                try:
                    ctx = change.elementContext
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d: backfill failed for designId=%s (tag=%s class=%s text=%s reactSource.file=%s)",
                        idx,
                        len(changes),
                        design_id,
                        getattr(ctx, "tagName", None),
                        _truncate_for_log(
                            str(getattr(ctx, "className", "") or ""), limit=160
                        ),
                        _truncate_for_log(
                            str(getattr(ctx, "textContent", "") or ""), limit=160
                        ),
                        (
                            (getattr(ctx, "reactSource", None) or {}).get("fileName")
                            if getattr(ctx, "reactSource", None)
                            else None
                        ),
                    )
                except Exception:
                    pass
                remaining.append(change)
                errors.append(
                    f'Change {idx}: Could not find data-design-id="{design_id}" in /workspace source'
                )
                continue

            resolved_path, content = backfilled
            logger.info(
                "[DesignMode Sync] (source-mapping) Change %d/%d: backfilled data-design-id=%s into %s",
                idx,
                len(changes),
                design_id,
                resolved_path,
            )

        if not isinstance(content, str) or not content:
            remaining.append(change)
            errors.append(f"Change {idx}: File is empty/unreadable: {resolved_path}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d: file empty/unreadable: %s",
                idx,
                len(changes),
                resolved_path,
            )
            continue
        if not isinstance(resolved_path, str) or not resolved_path:
            remaining.append(change)
            errors.append(
                f"Change {idx}: Missing/invalid resolved_path for designId={design_id}"
            )
            continue

        match_ok, mismatch_reason = _verify_design_mode_target_matches_context(
            change=change,
            content=content,
            file_path=resolved_path,
            design_id=design_id,
        )
        if not match_ok:
            if change.type == "style":
                to_value = None
                if isinstance(change.value, dict):
                    to_value = change.value.get("to")
                if to_value is not None:
                    css_ok, css_path = await _apply_style_change_as_css_override(
                        sandbox=sandbox,
                        manifest_path=manifest_path,
                        design_id=design_id,
                        css_prop=str(change.property or ""),
                        css_value="" if to_value is None else str(to_value),
                    )
                    if css_ok:
                        applied_count += 1
                        logger.info(
                            "[DesignMode Sync] (source-mapping) Change %d/%d applied as CSS override in %s (mismatch guard bypass)",
                            idx,
                            len(changes),
                            css_path,
                        )
                        continue

            remaining.append(change)
            errors.append(
                f'Change {idx}: data-design-id="{design_id}" matched an unexpected element in {resolved_path} ({mismatch_reason})'
            )
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d: mismatch guard blocked apply for designId=%s in %s (%s)",
                idx,
                len(changes),
                design_id,
                resolved_path,
                mismatch_reason,
            )
            continue

        updated_content = content
        did_apply = False

        if change.type == "style":
            to_value = None
            if isinstance(change.value, dict):
                to_value = change.value.get("to")
            if to_value is None:
                remaining.append(change)
                errors.append(f"Change {idx}: Missing style 'to' value")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing style 'to' value",
                    idx,
                    len(changes),
                )
                continue

            updated_content, did_apply = _apply_style_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
                css_prop=str(change.property or ""),
                css_value="" if to_value is None else str(to_value),
            )
        elif change.type == "text":
            from_value = None
            to_value = None
            if isinstance(change.value, dict):
                from_value = change.value.get("from")
                to_value = change.value.get("to")
            if not isinstance(from_value, str) or not isinstance(to_value, str):
                remaining.append(change)
                errors.append(f"Change {idx}: Missing text from/to values")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing text from/to values",
                    idx,
                    len(changes),
                )
                continue

            updated_content, did_apply = _apply_text_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
                old_text=from_value,
                new_text=to_value,
            )
        elif change.type == "move":
            to_value = None
            if isinstance(change.value, dict):
                to_value = change.value.get("to")
            if not isinstance(to_value, str) or not to_value:
                remaining.append(change)
                errors.append(f"Change {idx}: Missing move target")
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing move target",
                    idx,
                    len(changes),
                )
                continue

            # New format: anchor-based move (before:<id> / after:<id> / only).
            if (
                to_value == "only"
                or to_value.startswith("before:")
                or to_value.startswith("after:")
            ):
                if to_value == "only":
                    updated_content, did_apply = content, True
                else:
                    target_id = (
                        to_value.split(":", 1)[1].strip() if ":" in to_value else ""
                    )
                    if not target_id:
                        remaining.append(change)
                        errors.append(f"Change {idx}: Invalid move anchor '{to_value}'")
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d invalid move anchor: %s",
                            idx,
                            len(changes),
                            to_value,
                        )
                        continue

                    if not _find_opening_tag_bounds_for_design_id(content, target_id):
                        remaining.append(change)
                        errors.append(
                            f'Change {idx}: Could not find target data-design-id="{target_id}" in {resolved_path}'
                        )
                        logger.warning(
                            "[DesignMode Sync] (source-mapping) Change %d/%d move target designId not found in %s: %s",
                            idx,
                            len(changes),
                            resolved_path,
                            target_id,
                        )
                        continue

                    updated_content, did_apply = _apply_move_change_by_design_id_anchor(
                        content=content,
                        file_path=resolved_path,
                        design_id=design_id,
                        anchor=to_value,
                    )
            else:
                # Backward compatibility: older move changes used a raw swap target designId.
                target_id = to_value

                if not _find_opening_tag_bounds_for_design_id(content, target_id):
                    remaining.append(change)
                    errors.append(
                        f'Change {idx}: Could not find target data-design-id="{target_id}" in {resolved_path}'
                    )
                    logger.warning(
                        "[DesignMode Sync] (source-mapping) Change %d/%d target designId not found in %s: %s",
                        idx,
                        len(changes),
                        resolved_path,
                        target_id,
                    )
                    continue

                updated_content, did_apply = _apply_swap_change_by_design_ids(
                    content=content,
                    file_path=resolved_path,
                    design_id=design_id,
                    target_design_id=target_id,
                )
        elif change.type == "attribute" and change.property == "icon":
            # Handle icon changes
            icon_name, svg_inner = _extract_icon_payload_from_change(change)
            if not icon_name and not svg_inner:
                remaining.append(change)
                errors.append(
                    f"Change {idx}: Missing icon payload for attribute change"
                )
                logger.warning(
                    "[DesignMode Sync] (source-mapping) Change %d/%d missing icon payload",
                    idx,
                    len(changes),
                )
                continue

            updated_content, did_apply = _apply_icon_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
                icon_name=icon_name,
                svg_inner=svg_inner,
            )
            if not did_apply and icon_name:
                item_id = _extract_item_id_from_icon_design_id(design_id)
                if item_id:
                    updated_content, did_apply = (
                        _apply_icon_change_by_item_id_assignment(
                            content=content,
                            file_path=resolved_path,
                            item_id=item_id,
                            icon_name=icon_name,
                        )
                    )
        elif change.type == "delete":
            # Handle delete changes - remove the element from the source
            updated_content, did_apply = _apply_delete_change_by_design_id(
                content=content,
                file_path=resolved_path,
                design_id=design_id,
            )
        else:
            remaining.append(change)
            errors.append(f"Change {idx}: Unsupported change type '{change.type}'")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d unsupported type: %s",
                idx,
                len(changes),
                change.type,
            )
            continue

        if not did_apply:
            if change.type == "style":
                to_value = None
                if isinstance(change.value, dict):
                    to_value = change.value.get("to")
                if to_value is not None:
                    css_ok, css_path = await _apply_style_change_as_css_override(
                        sandbox=sandbox,
                        manifest_path=manifest_path,
                        design_id=design_id,
                        css_prop=str(change.property or ""),
                        css_value="" if to_value is None else str(to_value),
                    )
                    if css_ok:
                        applied_count += 1
                        logger.info(
                            "[DesignMode Sync] (source-mapping) Change %d/%d applied as CSS override in %s (source patch failed)",
                            idx,
                            len(changes),
                            css_path,
                        )
                        continue

            remaining.append(change)
            errors.append(f"Change {idx}: Could not apply change in {resolved_path}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d failed to apply in %s (designId=%s)",
                idx,
                len(changes),
                resolved_path,
                design_id,
            )
            continue

        try:
            await sandbox.write_file(resolved_path, updated_content)
            ok = True
        except Exception as exc:
            ok = False
            errors.append(f"Change {idx}: Failed to write {resolved_path}: {exc}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d failed to write %s: %s",
                idx,
                len(changes),
                resolved_path,
                exc,
            )

        if ok:
            applied_count += 1
            logger.info(
                "[DesignMode Sync] (source-mapping) Change %d/%d applied in %s",
                idx,
                len(changes),
                resolved_path,
            )
        else:
            remaining.append(change)
            errors.append(f"Change {idx}: Failed to persist changes to {resolved_path}")
            logger.warning(
                "[DesignMode Sync] (source-mapping) Change %d/%d failed to persist in %s",
                idx,
                len(changes),
                resolved_path,
            )

    await _emit_design_mode_sync_progress(
        emit_progress=emit_progress,
        session_id=session_id,
        processed=len(changes),
        total=len(changes),
        applied=applied_count,
        errors=len(errors),
        current=None,
        done=True,
    )
    return applied_count, errors, remaining


async def apply_changes_with_source_mapping(
    *,
    sandbox: Any,
    changes: List[StyleChange],
    session_id: Optional[uuid.UUID] = None,
    emit_progress: Optional[Callable[..., Awaitable[None]]] = None,
) -> tuple[int, List[str], List[StyleChange]]:
    return await _apply_changes_with_source_mapping(
        sandbox=sandbox,
        changes=changes,
        session_id=session_id,
        emit_progress=emit_progress,
    )


__all__ = ["apply_changes_with_source_mapping", "DESIGN_MODE_MANIFEST_FILENAME"]
