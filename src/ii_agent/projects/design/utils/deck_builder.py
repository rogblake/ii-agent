import re
from typing import List


def _extract_slide_head_and_body(html: str) -> tuple[str, str]:
    head_match = re.search(r"<head[^>]*>(.*?)</head>", html, flags=re.I | re.S)
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.I | re.S)

    head = head_match.group(1) if head_match else ""
    body = body_match.group(1) if body_match else html

    # Remove wrappers if the slide HTML didn't have a <body>.
    body = re.sub(r"<!doctype[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?html[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?head[^>]*>", "", body, flags=re.I)
    body = re.sub(r"</?body[^>]*>", "", body, flags=re.I)
    return head, body


def _scope_css_for_slide(css_text: str, slide_number: int) -> str:
    """
    Scope slide CSS to a container to reduce cross-slide style collisions in the deck.
    This mirrors the lightweight selector prefixing used in the frontend SlidesViewer.
    """

    slide_scope = f'[data-slide-number="{slide_number}"]'

    def repl(match: re.Match[str]) -> str:
        selector = match.group(1)
        # Skip outer @-blocks (but still allow inner selectors to be scoped).
        if "@keyframes" in selector or "@media" in selector:
            return match.group(0)

        parts: List[str] = []
        for raw in selector.split(","):
            sel = raw.strip()
            if not sel:
                continue

            if sel == ":root":
                parts.append(":root")
                continue
            if sel.startswith("@"):
                parts.append(sel)
                continue
            # Rewrite root selectors to target the slide canvas instead of the deck document body.
            if sel in ("html", "body"):
                sel = ".ii-slide-canvas"
            else:
                sel = re.sub(
                    r"^html\s+body(?=[\s.#:\[]|$)",
                    ".ii-slide-canvas",
                    sel,
                    flags=re.I,
                )
                sel = re.sub(
                    r"^body(?=[\s.#:\[]|$)",
                    ".ii-slide-canvas",
                    sel,
                    flags=re.I,
                )
                sel = re.sub(
                    r"^html(?=[\s.#:\[]|$)",
                    ".ii-slide-canvas",
                    sel,
                    flags=re.I,
                )
            if sel == "*":
                parts.append(f"{slide_scope} *")
                continue

            parts.append(f"{slide_scope} {sel}")

        if not parts:
            return match.group(0)
        return ", ".join(parts) + " {"

    return re.sub(r"([^{}]+){", repl, css_text)


def build_slide_deck_html(slides: List[tuple[int, str]]) -> str:
    """
    Build a single HTML document containing all slides stacked vertically.
    """

    links: List[str] = []
    scoped_styles: List[str] = []
    slide_sections: List[str] = []

    for slide_number, html in slides:
        if not slide_number:
            continue
        if not html or not html.strip():
            continue

        head, body = _extract_slide_head_and_body(html)

        # Collect and strip style tags from both head and body.
        style_texts = re.findall(r"<style[^>]*>(.*?)</style>", head, flags=re.I | re.S)
        style_texts += re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.I | re.S)
        body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.I | re.S)

        # Collect link tags (fonts, etc.).
        # NOTE: Use `\\b` only for regex word-boundary; raw strings should contain `\b`, not `\\b`.
        links.extend(re.findall(r"<link\b[^>]*>", head, flags=re.I))

        # Scope inline styles.
        for css in style_texts:
            scoped_styles.append(_scope_css_for_slide(css, slide_number))

        slide_sections.append(
            f"""
<div class="ii-slide-wrapper" data-slide-number="{slide_number}" data-design-scaffold="true">
  <div class="ii-slide-canvas" data-design-scaffold="true">
    {body}
  </div>
</div>
""".strip()
        )

    # De-duplicate link tags by exact text.
    unique_links: List[str] = []
    seen = set()
    for link in links:
        normalized = link.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_links.append(normalized)

    deck_base_css = """
html, body {
  margin: 0;
  padding: 0;
  background: #e5e7eb;
}
.ii-slide-deck {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  padding: 20px;
  box-sizing: border-box;
}
	.ii-slide-wrapper {
	  background: #ffffff;
	  border: 1px solid rgba(0,0,0,0.08);
	  border-radius: 12px;
	  overflow: hidden;
	  box-shadow: 0 18px 60px rgba(0,0,0,0.12);
	  display: inline-block;
	}
	.ii-slide-canvas {
	  overflow: hidden;
	  pointer-events: auto;
	  position: relative;
	  display: inline-block;
	}
	""".strip()

    combined_styles = "\n\n".join(scoped_styles)

    head_parts: List[str] = [
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        f"<style>{deck_base_css}</style>",
        "\n".join(unique_links),
        f"<style>{combined_styles}</style>" if combined_styles else "",
    ]
    head_html = "\n".join([p for p in head_parts if p.strip()])
    body_html = (
        '\n<div class="ii-slide-deck" data-design-scaffold="true">\n'
        + "\n".join(slide_sections)
        + "\n</div>\n"
    )

    return f"<!doctype html><html><head>{head_html}</head><body>{body_html}</body></html>"
