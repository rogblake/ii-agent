"""Tests for _tag_utils.py."""

from ii_agent.projects.design.source_mapping_sync._tag_utils import (
    _extract_closing_tag_name,
    _extract_opening_tag_name,
    _find_element_span_for_design_id,
    _find_matching_closing_tag_end,
    _find_opening_tag_bounds_for_design_id,
    _find_tag_end,
    _is_html_tag_name_for_design_mode,
    _normalize_whitespace_for_match,
    _tag_name_matches_for_design_mode,
)


# ---------------------------------------------------------------------------
# _extract_opening_tag_name
# ---------------------------------------------------------------------------


class TestExtractOpeningTagName:
    def test_simple_div(self):
        assert _extract_opening_tag_name("<div>") == "div"

    def test_with_attributes(self):
        assert _extract_opening_tag_name('<div class="foo">') == "div"

    def test_self_closing(self):
        assert _extract_opening_tag_name("<br />") == "br"

    def test_component(self):
        assert _extract_opening_tag_name("<MyComponent prop='a'>") == "MyComponent"

    def test_none_input(self):
        assert _extract_opening_tag_name(None) is None

    def test_empty_string(self):
        assert _extract_opening_tag_name("") is None

    def test_non_tag(self):
        assert _extract_opening_tag_name("not a tag") is None


# ---------------------------------------------------------------------------
# _extract_closing_tag_name
# ---------------------------------------------------------------------------


class TestExtractClosingTagName:
    def test_closing_div(self):
        assert _extract_closing_tag_name("</div>") == "div"

    def test_closing_with_spaces(self):
        assert _extract_closing_tag_name("</  span >") == "span"

    def test_none_input(self):
        assert _extract_closing_tag_name(None) is None

    def test_empty_string(self):
        assert _extract_closing_tag_name("") is None

    def test_opening_tag_returns_none(self):
        assert _extract_closing_tag_name("<div>") is None


# ---------------------------------------------------------------------------
# _find_tag_end
# ---------------------------------------------------------------------------


class TestFindTagEnd:
    def test_simple_tag(self):
        text = '<div class="foo">'
        assert _find_tag_end(text, 0) == len(text) - 1

    def test_quoted_greater_than(self):
        text = '<div title="a>b">'
        assert _find_tag_end(text, 0) == len(text) - 1

    def test_jsx_braces(self):
        text = "<div onClick={() => {}}>rest"
        result = _find_tag_end(text, 0)
        assert result is not None
        assert text[result] == ">"

    def test_self_closing(self):
        text = "<br />"
        assert _find_tag_end(text, 0) == len(text) - 1

    def test_no_close(self):
        assert _find_tag_end("<div", 0) is None

    def test_nested_braces(self):
        text = '<div style={{ color: "red" }}>rest'
        result = _find_tag_end(text, 0)
        assert result is not None
        assert text[result] == ">"

    def test_escaped_quotes(self):
        text = r'<div title="a\"b">'
        result = _find_tag_end(text, 0)
        assert result is not None

    def test_start_index_mid_string(self):
        text = 'xx<div class="hi">rest'
        assert _find_tag_end(text, 2) == text.index(">")


# ---------------------------------------------------------------------------
# _is_html_tag_name_for_design_mode
# ---------------------------------------------------------------------------


class TestIsHtmlTagNameForDesignMode:
    def test_html_tag(self):
        assert _is_html_tag_name_for_design_mode("div") is True

    def test_svg_tag(self):
        assert _is_html_tag_name_for_design_mode("path") is True

    def test_react_component(self):
        assert _is_html_tag_name_for_design_mode("MyComponent") is False

    def test_case_insensitive(self):
        assert _is_html_tag_name_for_design_mode("DIV") is True

    def test_empty(self):
        assert _is_html_tag_name_for_design_mode("") is False


# ---------------------------------------------------------------------------
# _tag_name_matches_for_design_mode
# ---------------------------------------------------------------------------


class TestTagNameMatchesForDesignMode:
    def test_same_html(self):
        assert _tag_name_matches_for_design_mode("div", "div") is True

    def test_case_insensitive_html(self):
        assert _tag_name_matches_for_design_mode("DIV", "div") is True

    def test_react_exact(self):
        assert _tag_name_matches_for_design_mode("Button", "Button") is True

    def test_react_mismatch(self):
        # React components (non-HTML tags) require exact case match
        assert _tag_name_matches_for_design_mode("MyButton", "MyInput") is False

    def test_empty_a(self):
        assert _tag_name_matches_for_design_mode("", "div") is False

    def test_empty_b(self):
        assert _tag_name_matches_for_design_mode("div", "") is False


# ---------------------------------------------------------------------------
# _find_matching_closing_tag_end
# ---------------------------------------------------------------------------


class TestFindMatchingClosingTagEnd:
    def test_simple(self):
        content = "<div>hello</div>"
        # Start searching after the opening tag
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result is not None
        assert content[result] == ">"

    def test_nested_same_tag(self):
        content = "<div><div>inner</div>outer</div>"
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result is not None
        # Should find the outer </div>, not inner
        assert content[result] == ">"
        assert result == len(content) - 1

    def test_self_closing_skip(self):
        content = "<div><br />text</div>"
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result is not None
        assert content[result] == ">"

    def test_no_close(self):
        content = "<div>hello"
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result is None

    def test_html_comment(self):
        content = "<div><!-- comment --></div>"
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result is not None

    def test_empty_content(self):
        assert _find_matching_closing_tag_end("", 0, "div") is None

    def test_none_content(self):
        assert _find_matching_closing_tag_end(None, 0, "div") is None

    def test_none_tag_name(self):
        assert _find_matching_closing_tag_end("<div></div>", 5, None) is None


# ---------------------------------------------------------------------------
# _find_opening_tag_bounds_for_design_id
# ---------------------------------------------------------------------------


class TestFindOpeningTagBoundsForDesignId:
    def test_double_quoted(self):
        content = '<div data-design-id="abc">text</div>'
        bounds = _find_opening_tag_bounds_for_design_id(content, "abc")
        assert bounds is not None
        tag_start, tag_end = bounds
        assert content[tag_start] == "<"
        assert content[tag_end] == ">"

    def test_single_quoted(self):
        content = "<div data-design-id='abc'>text</div>"
        bounds = _find_opening_tag_bounds_for_design_id(content, "abc")
        assert bounds is not None

    def test_full_bounds(self):
        content = '<span data-design-id="x1" class="foo">text</span>'
        bounds = _find_opening_tag_bounds_for_design_id(content, "x1")
        assert bounds is not None
        tag_start, tag_end = bounds
        tag = content[tag_start : tag_end + 1]
        assert tag.startswith("<span")
        assert 'data-design-id="x1"' in tag

    def test_not_found(self):
        content = '<div data-design-id="abc">text</div>'
        assert _find_opening_tag_bounds_for_design_id(content, "xyz") is None

    def test_empty_design_id(self):
        assert _find_opening_tag_bounds_for_design_id("<div>", "") is None

    def test_none_inputs(self):
        assert _find_opening_tag_bounds_for_design_id(None, "abc") is None
        assert _find_opening_tag_bounds_for_design_id("<div>", None) is None

    def test_nested_tag(self):
        content = '<section><div data-design-id="inner" class="x">hello</div></section>'
        bounds = _find_opening_tag_bounds_for_design_id(content, "inner")
        assert bounds is not None
        tag = content[bounds[0] : bounds[1] + 1]
        assert tag.startswith("<div")


# ---------------------------------------------------------------------------
# _find_element_span_for_design_id
# ---------------------------------------------------------------------------


class TestFindElementSpanForDesignId:
    def test_full_span(self):
        content = '<div data-design-id="a">hello</div>'
        span = _find_element_span_for_design_id(content, "a")
        assert span is not None
        assert content[span[0] : span[1]] == content

    def test_self_closing(self):
        content = '<br data-design-id="b" />'
        span = _find_element_span_for_design_id(content, "b")
        assert span is not None
        assert content[span[0] : span[1]] == content

    def test_nested(self):
        content = '<div data-design-id="outer"><span data-design-id="inner">text</span></div>'
        span = _find_element_span_for_design_id(content, "outer")
        assert span is not None
        assert content[span[0] : span[1]] == content

    def test_not_found(self):
        assert _find_element_span_for_design_id("<div>hi</div>", "nope") is None

    def test_unclosed(self):
        content = '<div data-design-id="x">no close'
        assert _find_element_span_for_design_id(content, "x") is None

    def test_none_input(self):
        assert _find_element_span_for_design_id(None, "a") is None


# ---------------------------------------------------------------------------
# _normalize_whitespace_for_match
# ---------------------------------------------------------------------------


class TestNormalizeWhitespaceForMatch:
    def test_collapse_spaces(self):
        assert _normalize_whitespace_for_match("a  b   c") == "a b c"

    def test_strip(self):
        assert _normalize_whitespace_for_match("  hello  ") == "hello"

    def test_empty(self):
        assert _normalize_whitespace_for_match("") == ""

    def test_none(self):
        assert _normalize_whitespace_for_match(None) == ""
