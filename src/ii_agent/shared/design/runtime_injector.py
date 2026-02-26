"""Runtime script injection and legacy artifact sanitization for design mode HTML."""

from __future__ import annotations

import re

from ii_agent.shared.design.constants import (
    DESIGN_MODE_GOOGLE_FONTS,
    DESIGN_MODE_RUNTIME_SCRIPT,
    EDITABLE_CLASS_NAMES,
)


def inject_runtime_script_only(html: str) -> str:
    """Inject Google Fonts and the runtime design-mode script into *html*."""
    injection = f"{DESIGN_MODE_GOOGLE_FONTS}\n{DESIGN_MODE_RUNTIME_SCRIPT}"

    if "<head>" in html:
        return html.replace("<head>", f"<head>\n{injection}\n", 1)
    if "<head " in html:
        return re.sub(
            r"(<head[^>]*>)",
            lambda m: f"{m.group(1)}\n{injection}\n",
            html,
            count=1,
        )
    if "<html>" in html or "<html " in html:
        return re.sub(
            r"(<html[^>]*>)",
            lambda m: f"{m.group(1)}\n<head>\n{injection}\n</head>\n",
            html,
            count=1,
        )
    return f"{injection}\n{html}"


def inject_runtime_script_with_base(html: str, base_url: str) -> str:
    """Inject Google Fonts, runtime script **and** a ``<base>`` tag into *html*."""
    base_tag = f'<base href="{base_url}" />'
    injection = f"{base_tag}\n{DESIGN_MODE_GOOGLE_FONTS}\n{DESIGN_MODE_RUNTIME_SCRIPT}"

    if "<head>" in html:
        return html.replace("<head>", f"<head>\n{injection}\n", 1)
    if "<head " in html:
        return re.sub(
            r"(<head[^>]*>)",
            lambda m: f"{m.group(1)}\n{injection}\n",
            html,
            count=1,
        )
    if "<html>" in html or "<html " in html:
        return re.sub(
            r"(<html[^>]*>)",
            lambda m: f"{m.group(1)}\n<head>\n{injection}\n</head>\n",
            html,
            count=1,
        )
    return f"{injection}\n{html}"


def sanitize_legacy_editable_artifacts(html: str) -> str:
    """Strip legacy editable-mode markup from *html*."""
    if not html or not html.strip():
        return html

    style_re = re.compile(r"<style[^>]*>(.*?)</style>", flags=re.I | re.S)

    def strip_style(match: re.Match[str]) -> str:
        css_text = match.group(1) or ""
        hay = css_text.lower()
        if ".editable" not in hay:
            return match.group(0)
        markers = ("#ff6b75", ".editable-img", ".drop-zone", ".image-preview")
        if any(marker in hay for marker in markers):
            return ""
        return match.group(0)

    html = style_re.sub(strip_style, html)

    span_re = re.compile(
        r"<span\b[^>]*\bdata-edit-id\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)[^>]*>(.*?)</span>",
        flags=re.I | re.S,
    )
    for _ in range(4):
        updated = span_re.sub(r"\1", html)
        if updated == html:
            break
        html = updated

    html = re.sub(
        r"\sdata-edit-id\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        html,
        flags=re.I,
    )
    html = re.sub(
        r"\sdata-img-id\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "",
        html,
        flags=re.I,
    )
    html = re.sub(
        r"\scontenteditable(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?",
        "",
        html,
        flags=re.I,
    )

    class_attr_re = re.compile(r"(\s+)class\s*=\s*(['\"])(.*?)\2", flags=re.I | re.S)

    def strip_classes(match: re.Match[str]) -> str:
        leading = match.group(1)
        quote = match.group(2)
        classes_raw = match.group(3) or ""
        classes = [part for part in re.split(r"\s+", classes_raw.strip()) if part]
        filtered = [item for item in classes if item not in EDITABLE_CLASS_NAMES]
        if not filtered:
            return ""
        return f"{leading}class={quote}{' '.join(filtered)}{quote}"

    return class_attr_re.sub(strip_classes, html)
