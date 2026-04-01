"""Unit tests for projects/design/utils/deck_builder.py."""

import pytest

from ii_agent.projects.design.utils.deck_builder import (
    _extract_slide_head_and_body,
    _scope_css_for_slide,
    build_slide_deck_html,
)


# ---------------------------------------------------------------------------
# _extract_slide_head_and_body tests
# ---------------------------------------------------------------------------


class TestExtractSlideHeadAndBody:
    """Tests for _extract_slide_head_and_body()."""

    def test_full_html_document(self):
        html = "<html><head><style>body{}</style></head><body><div>Hello</div></body></html>"
        head, body = _extract_slide_head_and_body(html)
        assert "<style>body{}</style>" in head
        assert "<div>Hello</div>" in body

    def test_document_without_head(self):
        html = "<html><body><div>Content</div></body></html>"
        head, body = _extract_slide_head_and_body(html)
        assert head == ""
        assert "Content" in body

    def test_document_without_body_uses_full_html(self):
        html = "<div>Just a fragment</div>"
        head, body = _extract_slide_head_and_body(html)
        assert head == ""
        assert "Just a fragment" in body

    def test_strips_doctype_from_body(self):
        html = "<!DOCTYPE html><html><body><p>Hi</p></body></html>"
        head, body = _extract_slide_head_and_body(html)
        assert "DOCTYPE" not in body

    def test_strips_html_tags_from_body(self):
        html = "<html><body><p>Content</p></body></html>"
        _, body = _extract_slide_head_and_body(html)
        assert "<html>" not in body
        assert "</html>" not in body

    def test_strips_head_tags_from_body(self):
        html = "<html><head></head><body><p>Content</p></body></html>"
        _, body = _extract_slide_head_and_body(html)
        assert "<head>" not in body
        assert "</head>" not in body

    def test_strips_body_tags_from_body(self):
        html = "<html><body><p>Content</p></body></html>"
        _, body = _extract_slide_head_and_body(html)
        assert "<body>" not in body
        assert "</body>" not in body

    def test_case_insensitive_tags(self):
        html = "<HTML><BODY><p>Text</p></BODY></HTML>"
        head, body = _extract_slide_head_and_body(html)
        assert "Text" in body

    def test_head_content_extracted_correctly(self):
        html = "<html><head><link rel='stylesheet' href='x.css'></head><body></body></html>"
        head, body = _extract_slide_head_and_body(html)
        assert "link" in head

    def test_empty_html(self):
        head, body = _extract_slide_head_and_body("")
        assert head == ""
        # Body defaults to the full html when no body tag


# ---------------------------------------------------------------------------
# _scope_css_for_slide tests
# ---------------------------------------------------------------------------


class TestScopeCssForSlide:
    """Tests for _scope_css_for_slide()."""

    def test_simple_selector_prefixed(self):
        css = ".foo { color: red; }"
        scoped = _scope_css_for_slide(css, slide_number=1)
        assert '[data-slide-number="1"] .foo' in scoped

    def test_body_selector_replaced_with_canvas(self):
        css = "body { margin: 0; }"
        scoped = _scope_css_for_slide(css, slide_number=2)
        assert '[data-slide-number="2"] .ii-slide-canvas' in scoped

    def test_html_selector_replaced_with_canvas(self):
        css = "html { font-size: 16px; }"
        scoped = _scope_css_for_slide(css, slide_number=1)
        assert ".ii-slide-canvas" in scoped

    def test_html_body_selector_replaced_with_canvas(self):
        css = "html body { background: #fff; }"
        scoped = _scope_css_for_slide(css, slide_number=1)
        assert ".ii-slide-canvas" in scoped

    def test_root_selector_preserved(self):
        css = ":root { --color: red; }"
        scoped = _scope_css_for_slide(css, slide_number=1)
        assert ":root" in scoped

    def test_wildcard_selector_prefixed(self):
        css = "* { box-sizing: border-box; }"
        scoped = _scope_css_for_slide(css, slide_number=3)
        assert '[data-slide-number="3"] *' in scoped

    def test_keyframes_preserved_in_output(self):
        css = "@keyframes fade { from { opacity: 0; } to { opacity: 1; } }"
        scoped = _scope_css_for_slide(css, slide_number=1)
        # @keyframes keyword is preserved in the output
        assert "@keyframes" in scoped

    def test_slide_number_used_correctly(self):
        css = ".item { font-size: 12px; }"
        scoped = _scope_css_for_slide(css, slide_number=5)
        assert '[data-slide-number="5"]' in scoped

    def test_comma_separated_selectors(self):
        css = "h1, h2 { font-weight: bold; }"
        scoped = _scope_css_for_slide(css, slide_number=1)
        assert "h1" in scoped
        assert "h2" in scoped

    def test_empty_css_handled(self):
        result = _scope_css_for_slide("", slide_number=1)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# build_slide_deck_html tests
# ---------------------------------------------------------------------------


class TestBuildSlideDeckHtml:
    """Tests for build_slide_deck_html()."""

    def _basic_slide(self, slide_number: int, content: str = "<p>Slide content</p>") -> tuple:
        return (slide_number, f"<html><head></head><body>{content}</body></html>")

    def test_returns_string(self):
        result = build_slide_deck_html([self._basic_slide(1)])
        assert isinstance(result, str)

    def test_contains_doctype(self):
        result = build_slide_deck_html([self._basic_slide(1)])
        assert "<!doctype html>" in result.lower()

    def test_contains_slide_deck_class(self):
        result = build_slide_deck_html([self._basic_slide(1)])
        assert "ii-slide-deck" in result

    def test_single_slide_contains_wrapper(self):
        result = build_slide_deck_html([self._basic_slide(1)])
        assert "ii-slide-wrapper" in result

    def test_slide_number_in_data_attribute(self):
        result = build_slide_deck_html([self._basic_slide(2)])
        assert 'data-slide-number="2"' in result

    def test_multiple_slides_all_present(self):
        slides = [
            self._basic_slide(1, "<p>Slide 1</p>"),
            self._basic_slide(2, "<p>Slide 2</p>"),
            self._basic_slide(3, "<p>Slide 3</p>"),
        ]
        result = build_slide_deck_html(slides)
        assert "Slide 1" in result
        assert "Slide 2" in result
        assert "Slide 3" in result

    def test_empty_slides_list(self):
        result = build_slide_deck_html([])
        assert isinstance(result, str)
        assert "ii-slide-deck" in result

    def test_slide_with_zero_number_skipped(self):
        slides = [(0, "<html><body><p>Skipped</p></body></html>")]
        result = build_slide_deck_html(slides)
        assert "Skipped" not in result

    def test_empty_slide_html_skipped(self):
        slides = [(1, ""), (2, "<html><body><p>Valid</p></body></html>")]
        result = build_slide_deck_html(slides)
        assert "Valid" in result

    def test_style_tags_scoped_to_slide(self):
        html = (
            "<html><head><style>.box { color: red; }</style></head>"
            "<body><div class='box'>Content</div></body></html>"
        )
        result = build_slide_deck_html([(1, html)])
        assert '[data-slide-number="1"]' in result

    def test_link_tags_deduplicated(self):
        font_link = '<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto">'
        html_with_font = f"<html><head>{font_link}</head><body><p>Text</p></body></html>"
        slides = [(1, html_with_font), (2, html_with_font)]
        result = build_slide_deck_html(slides)
        # Link should appear only once due to deduplication
        count = result.count("fonts.googleapis.com")
        assert count == 1

    def test_body_content_inside_canvas(self):
        result = build_slide_deck_html([self._basic_slide(1, "<h1>Title</h1>")])
        assert "ii-slide-canvas" in result
        assert "Title" in result

    def test_contains_base_css(self):
        result = build_slide_deck_html([self._basic_slide(1)])
        assert "ii-slide-deck" in result
        # Base CSS defines these classes
        assert "ii-slide-wrapper" in result
        assert "ii-slide-canvas" in result

    def test_style_tags_in_body_also_scoped(self):
        html = (
            "<html><body>"
            "<style>.btn { background: blue; }</style>"
            "<button class='btn'>Click</button>"
            "</body></html>"
        )
        result = build_slide_deck_html([(1, html)])
        assert '[data-slide-number="1"]' in result

    def test_slide_canvas_data_scaffold_attribute(self):
        result = build_slide_deck_html([self._basic_slide(1)])
        assert 'data-design-scaffold="true"' in result

    def test_whitespace_only_slide_skipped(self):
        # Whitespace-only HTML is skipped - no data-slide-number attribute in the body
        slides = [(1, "   \n\t  ")]
        result = build_slide_deck_html(slides)
        # The slide wrapper for slide 1 should NOT appear (slide was skipped)
        assert 'data-slide-number="1"' not in result
