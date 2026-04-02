import json
import re
from html import escape as escape_html
from typing import List, Optional, Tuple


def sanitize_slide_presentation_name(name: str) -> str:
    if not isinstance(name, str):
        return "presentation"
    sanitized = name.strip().replace(" ", "_")
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in ("_", "-"))
    return sanitized or "presentation"


def _find_tag_end(text: str, start_index: int) -> Optional[int]:
    if not isinstance(text, str) or not text:
        return None
    i = max(0, start_index)
    if i >= len(text) or text[i] != "<":
        return None

    quote: Optional[str] = None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
        else:
            if ch in {"'", '"'}:
                quote = ch
            elif ch == ">":
                return i
        i += 1
    return None


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


def _is_html_tag_name(value: str) -> bool:
    # Conservative heuristic: for slide HTML we only need this to handle <svg> and friends.
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9:_.-]*", (value or "").strip()))


def _tag_name_matches(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a = a.strip()
    b = b.strip()
    if _is_html_tag_name(a) and _is_html_tag_name(b):
        return a.lower() == b.lower()
    return a == b


def _find_matching_closing_tag_end(content: str, start_index: int, tag_name: str) -> Optional[int]:
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
            if name and _tag_name_matches(name, tag_name):
                depth -= 1
                if depth == 0:
                    return tag_end
        else:
            name = _extract_opening_tag_name(tag)
            if name and _tag_name_matches(name, tag_name):
                if not is_self_closing:
                    depth += 1

        i = tag_end + 1

    return None


def _find_opening_tag_bounds_for_design_id(
    content: str, design_id: str
) -> Optional[tuple[int, int]]:
    if not isinstance(content, str) or not content:
        return None
    if not isinstance(design_id, str) or not design_id:
        return None

    # Find the first tag containing data-design-id="<design_id>".
    pattern = rf'data-design-id=["\']{re.escape(design_id)}["\']'
    match = re.search(pattern, content)
    if not match:
        return None

    # Walk backwards to the opening '<'
    tag_start = content.rfind("<", 0, match.start())
    if tag_start == -1:
        return None
    tag_end = _find_tag_end(content, tag_start)
    if tag_end is None:
        return None
    return tag_start, tag_end


def _find_element_span_for_design_id(content: str, design_id: str) -> Optional[tuple[int, int]]:
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


def _parse_xpath(xpath: str) -> List[Tuple[str, int]]:
    """
    Parse a simple XPath into a list of (tag_name, index) tuples.
    Handles paths like /html/body/div/div[2]/section/div[3]
    Returns: [("html", 1), ("body", 1), ("div", 1), ("div", 2), ("section", 1), ("div", 3)]
    """
    if not xpath or not isinstance(xpath, str):
        return []

    parts = []
    segments = [s for s in xpath.split("/") if s.strip()]

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # Parse tag[index] format
        match = re.match(r"^([A-Za-z][A-Za-z0-9:_.-]*)\[(\d+)\]$", segment)
        if match:
            tag_name = match.group(1).lower()
            index = int(match.group(2))
            parts.append((tag_name, index))
        else:
            # No index means first occurrence
            tag_name = segment.lower()
            if re.match(r"^[A-Za-z][A-Za-z0-9:_.-]*$", tag_name):
                parts.append((tag_name, 1))

    return parts


def _strip_slide_deck_xpath_prefix(xpath: str, slide_number: int) -> Optional[str]:
    """
    Strip the slide deck wrapper prefix from an XPath.

    Deck structure is:
    /html/body/div/div[N]/div/... (where N is slide_number)

    Returns the XPath relative to the slide content, or None if not matching.
    """
    if not xpath or not isinstance(xpath, str):
        return None

    parts = _parse_xpath(xpath)
    if len(parts) < 5:
        return None

    # Check for expected deck wrapper structure
    # /html/body/div(.ii-slide-deck)/div[N](.ii-slide-wrapper)/div(.ii-slide-canvas)/...
    expected_prefix = [
        ("html", 1),
        ("body", 1),
        ("div", 1),  # .ii-slide-deck
        ("div", slide_number),  # .ii-slide-wrapper
        ("div", 1),  # .ii-slide-canvas
    ]

    if parts[:5] != expected_prefix:
        # Try alternative: slide might be at div[1] if it's the first slide
        if slide_number == 1:
            alt_prefix = [
                ("html", 1),
                ("body", 1),
                ("div", 1),
                ("div", 1),
                ("div", 1),
            ]
            if parts[:5] != alt_prefix:
                return None
        else:
            return None

    # Return the remaining path
    remaining = parts[5:]
    if not remaining:
        return None

    # Rebuild xpath string
    rebuilt_parts = []
    for tag_name, index in remaining:
        if index == 1:
            rebuilt_parts.append(tag_name)
        else:
            rebuilt_parts.append(f"{tag_name}[{index}]")

    return "/" + "/".join(rebuilt_parts)


def _find_element_by_xpath_in_fragment(html: str, xpath: str) -> Optional[Tuple[int, int]]:
    """
    Find an element in HTML fragment by XPath (relative path within the fragment).
    Returns (start, end) indices of the element's full span (opening to closing tag).
    """
    if not html or not xpath:
        return None

    parts = _parse_xpath(xpath)
    if not parts:
        return None

    # Walk through the HTML finding each tag in sequence
    current_pos = 0
    current_content = html

    for i, (target_tag, target_index) in enumerate(parts):
        found_count = 0
        search_pos = 0

        while True:
            # Find next opening tag
            tag_start = current_content.find("<", search_pos)
            if tag_start == -1:
                return None

            # Skip comments and directives
            if tag_start + 1 < len(current_content):
                next_char = current_content[tag_start + 1]
                if next_char in {"!", "?", "/"}:
                    tag_end = _find_tag_end(current_content, tag_start)
                    if tag_end is None:
                        return None
                    search_pos = tag_end + 1
                    continue

            tag_end = _find_tag_end(current_content, tag_start)
            if tag_end is None:
                return None

            tag = current_content[tag_start : tag_end + 1]
            tag_name = _extract_opening_tag_name(tag)

            if tag_name and tag_name.lower() == target_tag:
                found_count += 1
                if found_count == target_index:
                    # Found the target element
                    is_last = i == len(parts) - 1

                    if is_last:
                        # For the last element, return full span
                        if tag.rstrip().endswith("/>"):
                            return (current_pos + tag_start, current_pos + tag_end + 1)

                        closing_end = _find_matching_closing_tag_end(
                            current_content, tag_end + 1, tag_name
                        )
                        if closing_end is None:
                            return None
                        return (current_pos + tag_start, current_pos + closing_end + 1)
                    else:
                        # Move into this element's content for next iteration
                        if tag.rstrip().endswith("/>"):
                            # Self-closing tag has no children
                            return None

                        closing_end = _find_matching_closing_tag_end(
                            current_content, tag_end + 1, tag_name
                        )
                        if closing_end is None:
                            return None

                        # Extract inner content
                        inner_start = tag_end + 1
                        # Find where closing tag starts
                        closing_tag_start = current_content.rfind(
                            "</", inner_start, closing_end + 1
                        )
                        if closing_tag_start == -1:
                            return None

                        current_pos += inner_start
                        current_content = current_content[inner_start:closing_tag_start]
                        break

            search_pos = tag_end + 1

        if found_count < target_index:
            return None

    return None


def _find_opening_tag_bounds_by_xpath(
    html: str, xpath: str, slide_number: Optional[int] = None
) -> Optional[Tuple[int, int]]:
    """
    Find the opening tag bounds of an element by XPath.
    If slide_number is provided, strips the deck wrapper prefix first.
    Returns (start, end) indices of the opening tag.
    """
    if not html or not xpath:
        return None

    # If slide_number is provided, try to strip deck prefix
    effective_xpath = xpath
    if slide_number is not None and slide_number > 0:
        stripped = _strip_slide_deck_xpath_prefix(xpath, slide_number)
        if stripped:
            effective_xpath = stripped

    span = _find_element_by_xpath_in_fragment(html, effective_xpath)
    if not span:
        return None

    start, end = span
    fragment = html[start:end]
    tag_end = _find_tag_end(fragment, 0)
    if tag_end is None:
        return None

    return (start, start + tag_end)


def _sanitize_css_value_for_html_attr(value: str, attr_quote: str = '"') -> str:
    """
    Sanitize a CSS value so it can be safely embedded in an HTML attribute.

    The key issue: CSS values like url("https://...") contain quotes that can
    break HTML attribute parsing if the same quote type is used.

    Solution:
    - For url() values, remove quotes entirely (valid CSS) or use opposite quote type
    - For other values containing the attribute quote, this is a data issue we can't fix

    Args:
        value: The CSS value to sanitize
        attr_quote: The quote character used for the HTML attribute ('"' or "'")

    Returns:
        Sanitized CSS value safe for embedding in the HTML attribute
    """
    if not value:
        return value

    # Handle url() values - remove inner quotes entirely (valid CSS for most URLs)
    # url("https://example.com") -> url(https://example.com)
    # This is the safest approach as it works regardless of HTML attribute quote type
    result = re.sub(r'url\(["\']([^"\']*)["\']?\)', r"url(\1)", value)
    result = re.sub(r"url\(['\"]([^'\"]*)['\"]?\)", r"url(\1)", result)

    return result


def _extract_style_attribute_robust(tag: str) -> Optional[Tuple[int, int, str, str]]:
    """
    Extract the style attribute from an HTML tag using robust parsing.

    This handles edge cases like:
    - Corrupted/malformed style attributes
    - Style values containing various quote types
    - Case-insensitive attribute matching

    Returns (start_index, end_index, quote_char, style_content) or None.
    """
    # Case-insensitive search for style=
    tag_lower = tag.lower()
    style_idx = tag_lower.find("style=")
    if style_idx == -1:
        return None

    # Get the actual position in the original tag
    quote_pos = style_idx + 6  # len("style=")
    if quote_pos >= len(tag):
        return None

    quote = tag[quote_pos]
    if quote not in {'"', "'"}:
        return None

    # Find the end of the attribute value
    # We need to find the matching closing quote, but we must handle:
    # 1. The style content itself (which may have url() with inner quotes)
    # 2. Properly nested parentheses in CSS functions

    content_start = quote_pos + 1
    i = content_start
    paren_depth = 0

    while i < len(tag):
        ch = tag[i]

        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth = max(0, paren_depth - 1)
        elif ch == quote and paren_depth == 0:
            # Found the closing quote (not inside a CSS function)
            return (style_idx, i + 1, quote, tag[content_start:i])
        elif ch == ">" and paren_depth == 0:
            # Hit the end of the tag without finding closing quote
            # The attribute is malformed - return what we have
            return (style_idx, i, quote, tag[content_start:i])

        i += 1

    # Reached end of tag string without finding closing quote
    return None


def _remove_css_property(style_content: str, css_prop: str) -> str:
    """
    Remove a CSS property from a style string, handling complex values like url().

    Args:
        style_content: The existing style attribute content
        css_prop: The CSS property name to remove (e.g., "background-image")

    Returns:
        Style content with the property removed
    """
    if not style_content or not style_content.strip():
        return ""

    # Pattern to match the property we want to remove
    prop_pattern = re.compile(rf"^\s*{re.escape(css_prop)}\s*:", re.IGNORECASE)

    # Parse the style content into property:value pairs
    result = []
    i = 0

    while i < len(style_content):
        # Skip whitespace and semicolons between properties
        while i < len(style_content) and style_content[i] in " \t\n;":
            i += 1

        if i >= len(style_content):
            break

        # Find the end of this property:value pair
        # We need to handle parentheses for values like url(...)
        prop_start = i
        paren_depth = 0
        while i < len(style_content):
            ch = style_content[i]
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth = max(0, paren_depth - 1)
            elif ch == ";" and paren_depth == 0:
                # Found the end of this property
                break
            i += 1

        prop_value = style_content[prop_start:i].strip()

        # Keep this property unless it matches the one we want to remove
        if prop_value and not prop_pattern.match(prop_value):
            result.append(prop_value)

        # Skip past the semicolon
        if i < len(style_content) and style_content[i] == ";":
            i += 1

    return "; ".join(result)


def apply_slide_style_change_with_status(
    html: str,
    design_id: str,
    prop: str,
    value: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> tuple[str, bool]:
    # Convert camelCase to kebab-case for CSS property names
    css_prop = re.sub(r"([A-Z])", r"-\1", prop).lower().lstrip("-")

    # First try to find by design_id
    bounds = _find_opening_tag_bounds_for_design_id(html, design_id)

    # If design_id not found, try XPath fallback
    if not bounds and xpath:
        bounds = _find_opening_tag_bounds_by_xpath(html, xpath, slide_number)

    if not bounds:
        return html, False

    tag_start, tag_end = bounds
    opening_tag = html[tag_start : tag_end + 1]

    # Determine the quote character we'll use for the style attribute
    # Default to double quotes for new attributes
    attr_quote = '"'

    # Check if tag already has style attribute
    style_info = _extract_style_attribute_robust(opening_tag)
    if style_info:
        attr_start, attr_end, existing_quote, existing_style = style_info
        attr_quote = existing_quote

        # Remove the old property value if it exists
        existing_style = _remove_css_property(existing_style, css_prop)

        # Sanitize the new value for safe embedding in HTML attribute
        safe_value = _sanitize_css_value_for_html_attr(value, attr_quote) if value else ""

        if safe_value:
            new_style = (
                f"{existing_style.rstrip('; ')}"
                f"{'; ' if existing_style.strip() else ''}"
                f"{css_prop}: {safe_value};"
            )
        else:
            new_style = existing_style.rstrip("; ")

        new_opening_tag = (
            opening_tag[:attr_start]
            + f"style={attr_quote}{new_style}{attr_quote}"
            + opening_tag[attr_end:]
        )
    else:
        # Add new style attribute
        # Sanitize the value for safe embedding
        safe_value = _sanitize_css_value_for_html_attr(value, attr_quote) if value else ""

        if safe_value:
            # Insert style before the closing >
            if opening_tag.rstrip().endswith("/>"):
                insert_pos = opening_tag.rfind("/>")
                new_opening_tag = (
                    opening_tag[:insert_pos].rstrip() + f' style="{css_prop}: {safe_value};" />'
                )
            else:
                insert_pos = opening_tag.rfind(">")
                new_opening_tag = opening_tag[:insert_pos] + f' style="{css_prop}: {safe_value};">'
        else:
            new_opening_tag = opening_tag

    if new_opening_tag != opening_tag:
        new_html = html[:tag_start] + new_opening_tag + html[tag_end + 1 :]
        return new_html, True

    return html, False


def _find_element_span_with_fallback(
    html: str,
    design_id: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> Optional[Tuple[int, int]]:
    """
    Find element span by design_id first, then try XPath fallback.
    Returns (start, end) indices of the element's full span.
    """
    # First try design_id lookup
    span = _find_element_span_for_design_id(html, design_id)
    if span:
        return span

    # Try XPath fallback
    if xpath:
        span = _find_element_by_xpath_in_fragment(
            html,
            _strip_slide_deck_xpath_prefix(xpath, slide_number or 1) or xpath,
        )
        if span:
            return span

    return None


def apply_slide_text_change_with_status(
    html: str,
    design_id: str,
    text: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> tuple[str, bool]:
    span = _find_element_span_with_fallback(html, design_id, xpath, slide_number)
    if not span:
        return html, False

    start, end = span
    fragment = html[start:end]

    open_tag_end = _find_tag_end(fragment, 0)
    if open_tag_end is None:
        return html, False

    opening_tag = fragment[: open_tag_end + 1]
    if opening_tag.rstrip().endswith("/>"):
        return html, False

    close_tag_start = fragment.rfind("</", open_tag_end + 1)
    if close_tag_start == -1:
        return html, False

    inner_html = fragment[open_tag_end + 1 : close_tag_start]
    safe_text = escape_html(text if isinstance(text, str) else "", quote=False)

    void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    patched_parts: list[str] = []
    i = 0
    depth = 0
    replaced_any = False

    while i < len(inner_html):
        lt = inner_html.find("<", i)
        if lt == -1:
            segment = inner_html[i:]
            if depth == 0:
                if segment.strip():
                    if not replaced_any:
                        patched_parts.append(safe_text)
                        replaced_any = True
                    # Subsequent non-empty direct text nodes are cleared (matches runtime).
                else:
                    patched_parts.append(segment)
            else:
                patched_parts.append(segment)
            break

        segment = inner_html[i:lt]
        if depth == 0:
            if segment.strip():
                if not replaced_any:
                    patched_parts.append(safe_text)
                    replaced_any = True
            else:
                patched_parts.append(segment)
        else:
            patched_parts.append(segment)

        tag_end = _find_tag_end(inner_html, lt)
        if tag_end is None:
            patched_parts.append(inner_html[lt:])
            break

        tag = inner_html[lt : tag_end + 1]
        patched_parts.append(tag)

        tag_l = tag.lower()
        if tag_l.startswith("<!--") or tag_l.startswith("<!") or tag_l.startswith("<?"):
            pass
        elif tag_l.startswith("</"):
            if depth > 0:
                depth -= 1
        else:
            if tag.rstrip().endswith("/>"):
                pass
            else:
                name = (_extract_opening_tag_name(tag) or "").lower()
                if name and name not in void_tags:
                    depth += 1

        i = tag_end + 1

    if replaced_any:
        updated_inner = "".join(patched_parts)
    else:
        has_element_children = bool(re.search(r"<\s*[A-Za-z]", inner_html))
        updated_inner = safe_text if not has_element_children else safe_text + inner_html

    updated_fragment = fragment[: open_tag_end + 1] + updated_inner + fragment[close_tag_start:]
    updated_html = html[:start] + updated_fragment + html[end:]
    return updated_html, True


def apply_slide_icon_change_with_status(
    html: str,
    design_id: str,
    icon_data: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> tuple[str, bool]:
    """
    Apply an icon change to slide HTML.

    Supports two icon formats:
    1. SVG icons (Lucide, etc.): Replace SVG inner content
    2. Material Icons (<i> or <span> with class containing 'material-icons'): Replace text content
    """

    # Parse icon_data - it may be JSON with {name, svg} or just raw SVG/icon name
    icon_name = ""
    svg_inner = ""
    try:
        data = json.loads(icon_data)
        icon_name = data.get("name", "")
        svg_inner = data.get("svg", "")
    except (json.JSONDecodeError, TypeError):
        # Might be raw SVG or icon name
        if icon_data.strip().startswith("<"):
            svg_inner = icon_data
        else:
            icon_name = icon_data

    # First, check if this is a Material Icons element (text-based icon)
    if icon_name:
        element_pattern = rf'(<(?:i|span)[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*>)(.*?)(</(?:i|span)>)'

        match = re.search(element_pattern, html, flags=re.DOTALL | re.IGNORECASE)
        if match:
            opening_tag = match.group(1) + design_id + match.group(2)
            if "material-icons" in opening_tag.lower() or "material-symbols" in opening_tag.lower():
                new_html = (
                    html[: match.start()]
                    + match.group(1)
                    + design_id
                    + match.group(2)
                    + icon_name
                    + match.group(4)
                    + html[match.end() :]
                )
                return new_html, True

    # If no SVG inner content and no Material Icon match, fail
    if not svg_inner:
        return html, False

    # Try to apply as SVG icon (design_id directly on the <svg>)
    pattern = rf'(<svg[^>]*data-design-id=["\']){re.escape(design_id)}(["\'][^>]*>)(.*?)(</svg>)'

    def replace_svg_content(m: re.Match[str]) -> str:
        return f"{m.group(1)}{design_id}{m.group(2)}{svg_inner}{m.group(4)}"

    new_html, count = re.subn(
        pattern, replace_svg_content, html, count=1, flags=re.DOTALL | re.IGNORECASE
    )
    if count > 0:
        return new_html, True

    # Fallback: design_id might be on a wrapper element rather than the <svg>.
    # Also try XPath fallback if design_id not found.
    span = _find_element_span_with_fallback(html, design_id, xpath, slide_number)
    if not span:
        return html, False

    start, end = span
    fragment = html[start:end]
    svg_start = fragment.lower().find("<svg")
    if svg_start == -1:
        wrapped_svg_base = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'style="vertical-align: middle;">'
            f"{svg_inner}</svg>"
        )

        wrapped_svg_with_gap = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" '
            'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" '
            'style="vertical-align: middle; margin-right: 0.35em;">'
            f"{svg_inner}</svg>"
        )

        material_pattern = r'(<(span|i)\b[^>]*class=["\'][^"\']*(?:material-icons|material-symbols[^"\']*)[^"\']*["\'][^>]*>)(.*?)(</\2>)'

        def replace_material(m: re.Match[str]) -> str:
            return f"{m.group(1)}{wrapped_svg_base}{m.group(4)}"

        replaced_fragment, count = re.subn(
            material_pattern,
            replace_material,
            fragment,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if count > 0:
            updated_html = html[:start] + replaced_fragment + html[end:]
            return updated_html, True

        # No existing <svg> or Material Icons element. In slide decks we still want `set_icon`
        # to work for "add icon" requests, so insert an inline SVG as the first child.
        open_tag_end = _find_tag_end(fragment, 0)
        if open_tag_end is None:
            return html, False

        opening_tag = fragment[: open_tag_end + 1]
        tag_name = (_extract_opening_tag_name(opening_tag) or "").lower()
        use_gap = tag_name in {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "span",
            "a",
            "button",
            "label",
            "li",
        }
        svg_to_insert = wrapped_svg_with_gap if use_gap else wrapped_svg_base
        inserted_fragment = (
            fragment[: open_tag_end + 1] + svg_to_insert + fragment[open_tag_end + 1 :]
        )
        updated_html = html[:start] + inserted_fragment + html[end:]
        return updated_html, True

    svg_open_end = _find_tag_end(fragment, svg_start)
    if svg_open_end is None:
        return html, False

    svg_open_tag = fragment[svg_start : svg_open_end + 1]
    svg_tag_name = _extract_opening_tag_name(svg_open_tag) or "svg"

    svg_close_end = _find_matching_closing_tag_end(fragment, svg_open_end + 1, svg_tag_name)
    if svg_close_end is None:
        return html, False

    svg_close_start = fragment.rfind("</", svg_open_end + 1, svg_close_end + 1)
    if svg_close_start == -1:
        return html, False

    updated_fragment = fragment[: svg_open_end + 1] + svg_inner + fragment[svg_close_start:]
    updated_html = html[:start] + updated_fragment + html[end:]
    return updated_html, True


def apply_slide_delete_change_with_status(
    html: str,
    *,
    design_id: str,
    file_path: str = "",
) -> tuple[str, bool]:
    """Delete an element identified by `data-design-id`."""
    span = _find_element_span_for_design_id(html, design_id)
    if not span:
        return html, False

    start, end = span

    # Trim leading whitespace when the element starts on its own line.
    line_start = start
    while line_start > 0 and html[line_start - 1] in " \t":
        line_start -= 1
    if line_start == 0 or html[line_start - 1] == "\n":
        start = line_start

    # Drop trailing newline for cleaner formatting.
    if end < len(html) and html[end] == "\n":
        end += 1

    updated = html[:start] + html[end:]
    return updated, True


def apply_slide_swap_change_with_status(
    html: str,
    *,
    design_id: str,
    target_design_id: str,
    file_path: str = "",
) -> tuple[str, bool]:
    """Swap two elements identified by design IDs."""
    span_a = _find_element_span_for_design_id(html, design_id)
    span_b = _find_element_span_for_design_id(html, target_design_id)
    if not span_a or not span_b:
        return html, False

    a_start, a_end = span_a
    b_start, b_end = span_b
    if a_start == b_start and a_end == b_end:
        return html, True

    if a_start > b_start:
        (a_start, a_end), (b_start, b_end) = (b_start, b_end), (a_start, a_end)

    if a_end > b_start:
        return html, False

    a_block = html[a_start:a_end]
    b_block = html[b_start:b_end]
    updated = html[:a_start] + b_block + html[a_end:b_start] + a_block + html[b_end:]
    return updated, True


def apply_slide_move_change_with_status(
    html: str,
    *,
    design_id: str,
    anchor: str,
    file_path: str = "",
) -> tuple[str, bool]:
    """Move an element relative to another design-id anchor.

    Anchor format:
    - `before:<target-design-id>`
    - `after:<target-design-id>`
    - `only` (treated as no-op success)
    """
    if not isinstance(anchor, str) or not anchor.strip():
        return html, False

    anchor = anchor.strip()
    if anchor == "only":
        return html, True

    if anchor.startswith("before:"):
        target_design_id = anchor.split(":", 1)[1].strip()
        if not target_design_id:
            return html, False
        return _apply_move_change_by_design_ids(
            html,
            design_id=design_id,
            target_design_id=target_design_id,
            mode="before",
        )

    if anchor.startswith("after:"):
        target_design_id = anchor.split(":", 1)[1].strip()
        if not target_design_id:
            return html, False
        return _apply_move_change_by_design_ids(
            html,
            design_id=design_id,
            target_design_id=target_design_id,
            mode="after",
        )

    # Legacy behavior: a bare value means swap target.
    return apply_slide_swap_change_with_status(
        html,
        design_id=design_id,
        target_design_id=anchor,
        file_path=file_path,
    )


def _apply_move_change_by_design_ids(
    html: str,
    *,
    design_id: str,
    target_design_id: str,
    mode: str,
) -> tuple[str, bool]:
    if design_id == target_design_id:
        return html, True
    if mode not in {"before", "after"}:
        return html, False

    span_a = _find_element_span_for_design_id(html, design_id)
    span_b = _find_element_span_for_design_id(html, target_design_id)
    if not span_a or not span_b:
        return html, False

    a_start, a_end = span_a
    b_start, b_end = span_b

    # Refuse nested/overlapping spans.
    if not (a_end <= b_start or b_end <= a_start):
        return html, False

    a_block = html[a_start:a_end]
    removed = html[:a_start] + html[a_end:]

    target_span_after_removal = _find_element_span_for_design_id(removed, target_design_id)
    if not target_span_after_removal:
        return html, False

    insert_at = target_span_after_removal[0] if mode == "before" else target_span_after_removal[1]
    updated = removed[:insert_at] + a_block + removed[insert_at:]
    return updated, True


def apply_slide_style_change(
    html: str,
    design_id: str,
    prop: str,
    value: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> str:
    updated, _ = apply_slide_style_change_with_status(
        html, design_id, prop, value, xpath, slide_number
    )
    return updated


def apply_slide_text_change(
    html: str,
    design_id: str,
    text: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> str:
    updated, _ = apply_slide_text_change_with_status(html, design_id, text, xpath, slide_number)
    return updated


def apply_slide_icon_change(
    html: str,
    design_id: str,
    icon_data: str,
    xpath: Optional[str] = None,
    slide_number: Optional[int] = None,
) -> str:
    updated, _ = apply_slide_icon_change_with_status(
        html, design_id, icon_data, xpath, slide_number
    )
    return updated


def apply_slide_delete_change(
    html: str,
    *,
    design_id: str,
    file_path: str = "",
) -> str:
    updated, _ = apply_slide_delete_change_with_status(
        html,
        design_id=design_id,
        file_path=file_path,
    )
    return updated


def apply_slide_move_change(
    html: str,
    *,
    design_id: str,
    anchor: str,
    file_path: str = "",
) -> str:
    updated, _ = apply_slide_move_change_with_status(
        html,
        design_id=design_id,
        anchor=anchor,
        file_path=file_path,
    )
    return updated


def apply_slide_swap_change(
    html: str,
    *,
    design_id: str,
    target_design_id: str,
    file_path: str = "",
) -> str:
    updated, _ = apply_slide_swap_change_with_status(
        html,
        design_id=design_id,
        target_design_id=target_design_id,
        file_path=file_path,
    )
    return updated
