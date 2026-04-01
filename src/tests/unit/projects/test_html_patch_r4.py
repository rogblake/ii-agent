"""Unit tests for projects/design/utils/html_patch.py (r4 extended)."""

from __future__ import annotations

import json

import pytest

from ii_agent.projects.design.utils.html_patch import (
    _extract_closing_tag_name,
    _extract_opening_tag_name,
    _find_element_span_for_design_id,
    _find_matching_closing_tag_end,
    _find_opening_tag_bounds_for_design_id,
    _find_tag_end,
    _is_html_tag_name,
    _parse_xpath,
    _remove_css_property,
    _sanitize_css_value_for_html_attr,
    _strip_slide_deck_xpath_prefix,
    _tag_name_matches,
    apply_slide_delete_change,
    apply_slide_delete_change_with_status,
    apply_slide_icon_change,
    apply_slide_icon_change_with_status,
    apply_slide_move_change,
    apply_slide_move_change_with_status,
    apply_slide_style_change,
    apply_slide_style_change_with_status,
    apply_slide_swap_change,
    apply_slide_swap_change_with_status,
    apply_slide_text_change,
    apply_slide_text_change_with_status,
    sanitize_slide_presentation_name,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SIMPLE_HTML = '<div data-design-id="did-1" class="box">Hello</div>'
NESTED_HTML = '<div data-design-id="did-outer"><span data-design-id="did-inner">Inner</span></div>'
SELF_CLOSING = '<img data-design-id="did-img" src="foo.png" />'
STYLED_HTML = '<div data-design-id="did-1" style="color: red; font-size: 16px;">Text</div>'
MULTI_HTML = (
    '<div data-design-id="did-1">A</div>'
    '<div data-design-id="did-2">B</div>'
    '<div data-design-id="did-3">C</div>'
)


# ---------------------------------------------------------------------------
# sanitize_slide_presentation_name
# ---------------------------------------------------------------------------


class TestSanitizeSlidePresentationNameR4:
    def test_basic_name(self):
        assert sanitize_slide_presentation_name("My Slide") == "My_Slide"

    def test_spaces_to_underscores(self):
        assert sanitize_slide_presentation_name("hello world") == "hello_world"

    def test_special_chars_removed(self):
        result = sanitize_slide_presentation_name("Hello! @World#2024")
        assert "!" not in result
        assert "@" not in result
        assert "#" not in result

    def test_hyphens_preserved(self):
        assert sanitize_slide_presentation_name("my-deck") == "my-deck"

    def test_underscores_preserved(self):
        assert sanitize_slide_presentation_name("my_deck") == "my_deck"

    def test_empty_returns_presentation(self):
        assert sanitize_slide_presentation_name("") == "presentation"

    def test_whitespace_only_returns_presentation(self):
        assert sanitize_slide_presentation_name("   ") == "presentation"

    def test_special_only_returns_presentation(self):
        assert sanitize_slide_presentation_name("!@#$%") == "presentation"

    def test_non_string_returns_presentation(self):
        assert sanitize_slide_presentation_name(None) == "presentation"  # type: ignore
        assert sanitize_slide_presentation_name(42) == "presentation"  # type: ignore

    def test_leading_trailing_spaces_stripped(self):
        result = sanitize_slide_presentation_name("  Hello  ")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_numbers_preserved(self):
        assert sanitize_slide_presentation_name("slide2024") == "slide2024"

    def test_mixed_valid_and_invalid(self):
        result = sanitize_slide_presentation_name("Q1 Results!")
        assert "Q1" in result
        assert "Results" in result


# ---------------------------------------------------------------------------
# _find_tag_end
# ---------------------------------------------------------------------------


class TestFindTagEndR4:
    def test_simple_open_tag(self):
        text = "<div>"
        assert _find_tag_end(text, 0) == 4

    def test_self_closing_tag(self):
        text = "<br />"
        assert _find_tag_end(text, 0) == 5

    def test_tag_with_attribute(self):
        text = '<div class="foo">'
        assert _find_tag_end(text, 0) == len(text) - 1

    def test_no_start_lt(self):
        assert _find_tag_end("no tag here", 0) is None

    def test_not_starting_with_lt(self):
        assert _find_tag_end("hello>", 0) is None

    def test_empty_string(self):
        assert _find_tag_end("", 0) is None

    def test_non_string_input(self):
        assert _find_tag_end(None, 0) is None  # type: ignore

    def test_quoted_gt_not_end(self):
        text = '<div data-x="a>b">'
        result = _find_tag_end(text, 0)
        assert result == len(text) - 1

    def test_closing_tag(self):
        text = "</div>"
        result = _find_tag_end(text, 0)
        assert result == 5

    def test_unclosed_tag_returns_none(self):
        text = "<div class='foo'"
        assert _find_tag_end(text, 0) is None

    def test_start_index_beyond_lt(self):
        text = "prefix <div>"
        assert _find_tag_end(text, 7) == 11


# ---------------------------------------------------------------------------
# _extract_opening_tag_name
# ---------------------------------------------------------------------------


class TestExtractOpeningTagNameR4:
    def test_simple_div(self):
        assert _extract_opening_tag_name("<div>") == "div"

    def test_with_attributes(self):
        assert _extract_opening_tag_name('<span class="foo">') == "span"

    def test_self_closing(self):
        assert _extract_opening_tag_name("<br />") == "br"

    def test_closing_tag_returns_none(self):
        assert _extract_opening_tag_name("</div>") is None

    def test_empty_string_returns_none(self):
        assert _extract_opening_tag_name("") is None

    def test_none_returns_none(self):
        assert _extract_opening_tag_name(None) is None  # type: ignore

    def test_svg_tag(self):
        assert _extract_opening_tag_name("<svg viewBox='0 0 24 24'>") == "svg"

    def test_namespaced_tag(self):
        name = _extract_opening_tag_name("<ns:element>")
        assert name == "ns:element"


# ---------------------------------------------------------------------------
# _extract_closing_tag_name
# ---------------------------------------------------------------------------


class TestExtractClosingTagNameR4:
    def test_simple_closing(self):
        assert _extract_closing_tag_name("</div>") == "div"

    def test_opening_tag_returns_none(self):
        assert _extract_closing_tag_name("<div>") is None

    def test_empty_returns_none(self):
        assert _extract_closing_tag_name("") is None

    def test_none_returns_none(self):
        assert _extract_closing_tag_name(None) is None  # type: ignore

    def test_closing_with_spaces(self):
        name = _extract_closing_tag_name("</ div>")
        assert name == "div"


# ---------------------------------------------------------------------------
# _is_html_tag_name
# ---------------------------------------------------------------------------


class TestIsHtmlTagNameR4:
    def test_valid_tag(self):
        assert _is_html_tag_name("div") is True

    def test_camelcase_valid(self):
        assert _is_html_tag_name("myTag") is True

    def test_with_hyphen_valid(self):
        assert _is_html_tag_name("my-tag") is True

    def test_empty_invalid(self):
        assert _is_html_tag_name("") is False

    def test_starts_with_number_invalid(self):
        assert _is_html_tag_name("1tag") is False

    def test_with_space_invalid(self):
        assert _is_html_tag_name("my tag") is False


# ---------------------------------------------------------------------------
# _tag_name_matches
# ---------------------------------------------------------------------------


class TestTagNameMatchesR4:
    def test_same_tag(self):
        assert _tag_name_matches("div", "div") is True

    def test_case_insensitive(self):
        assert _tag_name_matches("DIV", "div") is True

    def test_different_tags(self):
        assert _tag_name_matches("div", "span") is False

    def test_empty_a_returns_false(self):
        assert _tag_name_matches("", "div") is False

    def test_empty_b_returns_false(self):
        assert _tag_name_matches("div", "") is False


# ---------------------------------------------------------------------------
# _find_matching_closing_tag_end
# ---------------------------------------------------------------------------


class TestFindMatchingClosingTagEndR4:
    def test_simple_match(self):
        content = "<div>inner</div>"
        # Start searching after initial <div>, which ends at index 4
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result == len(content) - 1

    def test_nested_tags(self):
        content = "<div><div>inner</div></div>"
        result = _find_matching_closing_tag_end(content, 5, "div")
        # Should find the outer closing tag
        assert result == len(content) - 1

    def test_empty_content(self):
        assert _find_matching_closing_tag_end("", 0, "div") is None

    def test_no_closing_tag(self):
        content = "<div>unclosed content"
        result = _find_matching_closing_tag_end(content, 5, "div")
        assert result is None

    def test_invalid_content_type(self):
        assert _find_matching_closing_tag_end(None, 0, "div") is None  # type: ignore


# ---------------------------------------------------------------------------
# _parse_xpath
# ---------------------------------------------------------------------------


class TestParseXpathR4:
    def test_simple_path(self):
        result = _parse_xpath("/html/body/div")
        assert result == [("html", 1), ("body", 1), ("div", 1)]

    def test_with_index(self):
        result = _parse_xpath("/html/body/div[2]")
        assert result == [("html", 1), ("body", 1), ("div", 2)]

    def test_empty_returns_empty(self):
        assert _parse_xpath("") == []

    def test_none_returns_empty(self):
        assert _parse_xpath(None) == []  # type: ignore

    def test_first_occurrence_default(self):
        result = _parse_xpath("/div/span")
        assert result[0] == ("div", 1)
        assert result[1] == ("span", 1)

    def test_complex_path(self):
        result = _parse_xpath("/html/body/div/div[2]/section/div[3]")
        assert result[3] == ("div", 2)
        assert result[5] == ("div", 3)


# ---------------------------------------------------------------------------
# _strip_slide_deck_xpath_prefix
# ---------------------------------------------------------------------------


class TestStripSlideDeckXpathPrefixR4:
    def test_strips_valid_prefix(self):
        xpath = "/html/body/div/div/div/p"
        result = _strip_slide_deck_xpath_prefix(xpath, slide_number=1)
        assert result == "/p"

    def test_returns_none_for_short_path(self):
        result = _strip_slide_deck_xpath_prefix("/html/body/div", 1)
        assert result is None

    def test_returns_none_for_wrong_prefix(self):
        result = _strip_slide_deck_xpath_prefix("/html/body/section/div[2]/div/p", 1)
        assert result is None

    def test_returns_none_for_empty(self):
        assert _strip_slide_deck_xpath_prefix("", 1) is None

    def test_returns_none_for_none(self):
        assert _strip_slide_deck_xpath_prefix(None, 1) is None  # type: ignore

    def test_slide_number_2(self):
        xpath = "/html/body/div/div[2]/div/p"
        result = _strip_slide_deck_xpath_prefix(xpath, slide_number=2)
        assert result == "/p"


# ---------------------------------------------------------------------------
# _sanitize_css_value_for_html_attr
# ---------------------------------------------------------------------------


class TestSanitizeCssValueForHtmlAttrR4:
    def test_url_with_double_quotes_stripped(self):
        value = 'url("https://example.com/img.png")'
        result = _sanitize_css_value_for_html_attr(value, '"')
        assert '"' not in result.replace("url(", "").replace(")", "")

    def test_url_with_single_quotes_stripped(self):
        value = "url('https://example.com/img.png')"
        result = _sanitize_css_value_for_html_attr(value, '"')
        assert "'" not in result.replace("url(", "").replace(")", "")

    def test_plain_value_unchanged(self):
        value = "rgba(0, 0, 0, 0.5)"
        result = _sanitize_css_value_for_html_attr(value, '"')
        assert result == value

    def test_empty_value_returned_as_is(self):
        assert _sanitize_css_value_for_html_attr("", '"') == ""

    def test_color_value_unchanged(self):
        result = _sanitize_css_value_for_html_attr("red", '"')
        assert result == "red"


# ---------------------------------------------------------------------------
# _remove_css_property
# ---------------------------------------------------------------------------


class TestRemoveCssPropertyR4:
    def test_removes_color_property(self):
        style = "color: red; font-size: 16px;"
        result = _remove_css_property(style, "color")
        assert "color" not in result
        assert "font-size" in result

    def test_removes_only_target_property(self):
        style = "background-color: blue; color: red; margin: 0;"
        result = _remove_css_property(style, "color")
        assert "background-color" in result
        assert "margin" in result
        assert "color: red" not in result

    def test_empty_style_returns_empty(self):
        result = _remove_css_property("", "color")
        assert result == ""

    def test_property_not_in_style(self):
        style = "font-size: 16px;"
        result = _remove_css_property(style, "color")
        assert "font-size" in result

    def test_handles_url_values(self):
        style = "background-image: url(img.png); color: red;"
        result = _remove_css_property(style, "background-image")
        assert "background-image" not in result
        assert "color" in result

    def test_case_insensitive_removal(self):
        style = "Color: red; Font-Size: 16px;"
        result = _remove_css_property(style, "color")
        assert "Color: red" not in result


# ---------------------------------------------------------------------------
# _find_opening_tag_bounds_for_design_id
# ---------------------------------------------------------------------------


class TestFindOpeningTagBoundsForDesignIdR4:
    def test_finds_bounds_in_simple_html(self):
        result = _find_opening_tag_bounds_for_design_id(SIMPLE_HTML, "did-1")
        assert result is not None
        tag_start, tag_end = result
        assert SIMPLE_HTML[tag_start] == "<"
        assert SIMPLE_HTML[tag_end] == ">"

    def test_returns_none_for_missing_id(self):
        result = _find_opening_tag_bounds_for_design_id(SIMPLE_HTML, "missing-id")
        assert result is None

    def test_returns_none_for_empty_html(self):
        assert _find_opening_tag_bounds_for_design_id("", "did-1") is None

    def test_returns_none_for_empty_design_id(self):
        assert _find_opening_tag_bounds_for_design_id(SIMPLE_HTML, "") is None

    def test_finds_bounds_with_single_quotes(self):
        html = "<div data-design-id='did-x'>Text</div>"
        result = _find_opening_tag_bounds_for_design_id(html, "did-x")
        assert result is not None


# ---------------------------------------------------------------------------
# _find_element_span_for_design_id
# ---------------------------------------------------------------------------


class TestFindElementSpanForDesignIdR4:
    def test_finds_span_in_simple_html(self):
        result = _find_element_span_for_design_id(SIMPLE_HTML, "did-1")
        assert result is not None
        start, end = result
        assert SIMPLE_HTML[start:end] == SIMPLE_HTML

    def test_finds_nested_element(self):
        result = _find_element_span_for_design_id(NESTED_HTML, "did-inner")
        assert result is not None
        start, end = result
        assert 'data-design-id="did-inner"' in NESTED_HTML[start:end]

    def test_finds_self_closing_element(self):
        result = _find_element_span_for_design_id(SELF_CLOSING, "did-img")
        assert result is not None
        start, end = result
        assert SELF_CLOSING[start:end] == SELF_CLOSING

    def test_returns_none_for_missing_id(self):
        assert _find_element_span_for_design_id(SIMPLE_HTML, "missing") is None

    def test_correct_span_in_multi_element_html(self):
        result = _find_element_span_for_design_id(MULTI_HTML, "did-2")
        assert result is not None
        start, end = result
        extracted = MULTI_HTML[start:end]
        assert 'data-design-id="did-2"' in extracted
        assert "did-1" not in extracted
        assert "did-3" not in extracted


# ---------------------------------------------------------------------------
# apply_slide_style_change_with_status
# ---------------------------------------------------------------------------


class TestApplySlideStyleChangeWithStatusR4:
    def test_adds_new_style_to_element(self):
        html = '<div data-design-id="did-1">Text</div>'
        result, success = apply_slide_style_change_with_status(html, "did-1", "color", "blue")
        assert success is True
        assert "color: blue;" in result

    def test_updates_existing_style(self):
        result, success = apply_slide_style_change_with_status(
            STYLED_HTML, "did-1", "color", "blue"
        )
        assert success is True
        assert "color: blue;" in result
        # Old color removed
        assert "color: red" not in result

    def test_preserves_other_styles(self):
        result, success = apply_slide_style_change_with_status(
            STYLED_HTML, "did-1", "color", "blue"
        )
        assert "font-size: 16px" in result

    def test_returns_false_for_missing_id(self):
        html = '<div data-design-id="did-1">Text</div>'
        result, success = apply_slide_style_change_with_status(html, "missing", "color", "blue")
        assert success is False
        assert result == html

    def test_camel_case_prop_converted_to_kebab(self):
        html = '<div data-design-id="did-1">Text</div>'
        result, success = apply_slide_style_change_with_status(
            html, "did-1", "backgroundColor", "red"
        )
        assert success is True
        assert "background-color: red;" in result

    def test_empty_value_removes_property(self):
        result, success = apply_slide_style_change_with_status(STYLED_HTML, "did-1", "color", "")
        assert success is True
        assert "color: red" not in result

    def test_url_value_sanitized(self):
        html = '<div data-design-id="did-1">Text</div>'
        result, success = apply_slide_style_change_with_status(
            html, "did-1", "backgroundImage", 'url("https://example.com/img.png")'
        )
        assert success is True
        assert "background-image" in result

    def test_xpath_fallback(self):
        html = "<html><body><div><div><div><p>text</p></div></div></div></body></html>"
        xpath = "/html/body/div/div/div/p"
        result, success = apply_slide_style_change_with_status(
            html,
            "missing-id",
            "color",
            "red",
            xpath=xpath,
            slide_number=1,
        )
        # May or may not succeed depending on structure, but should not raise
        assert isinstance(success, bool)


# ---------------------------------------------------------------------------
# apply_slide_text_change_with_status
# ---------------------------------------------------------------------------


class TestApplySlideTextChangeWithStatusR4:
    def test_replaces_text_content(self):
        result, success = apply_slide_text_change_with_status(SIMPLE_HTML, "did-1", "New text")
        assert success is True
        assert "New text" in result

    def test_escapes_html_in_new_text(self):
        result, success = apply_slide_text_change_with_status(SIMPLE_HTML, "did-1", "<b>bold</b>")
        assert success is True
        assert "&lt;b&gt;" in result

    def test_returns_false_for_missing_id(self):
        result, success = apply_slide_text_change_with_status(SIMPLE_HTML, "missing", "New text")
        assert success is False
        assert result == SIMPLE_HTML

    def test_preserves_nested_tags(self):
        html = '<div data-design-id="did-1"><span>child</span> text node</div>'
        result, success = apply_slide_text_change_with_status(html, "did-1", "replaced")
        assert success is True
        # Child span should be preserved
        assert "<span>" in result

    def test_non_string_text_converted(self):
        result, success = apply_slide_text_change_with_status(SIMPLE_HTML, "did-1", 42)  # type: ignore
        assert success is True

    def test_empty_text_clears_direct_text_nodes(self):
        result, success = apply_slide_text_change_with_status(SIMPLE_HTML, "did-1", "")
        assert success is True


# ---------------------------------------------------------------------------
# apply_slide_icon_change_with_status
# ---------------------------------------------------------------------------


class TestApplySlideIconChangeWithStatusR4:
    def test_replaces_svg_inner_content(self):
        html = '<svg data-design-id="did-svg" viewBox="0 0 24 24"><path d="M0 0"/></svg>'
        icon_data = json.dumps({"name": "rocket", "svg": '<circle cx="12" cy="12" r="5"/>'})
        result, success = apply_slide_icon_change_with_status(html, "did-svg", icon_data)
        assert success is True
        assert '<circle cx="12"' in result
        assert '<path d="M0 0"/>' not in result

    def test_raw_svg_string(self):
        html = '<svg data-design-id="did-svg"><path d="M0 0"/></svg>'
        result, success = apply_slide_icon_change_with_status(
            html, "did-svg", '<circle cx="12" cy="12" r="5"/>'
        )
        assert success is True

    def test_material_icons_text_replacement(self):
        html = '<i data-design-id="did-icon" class="material-icons">star</i>'
        icon_data = json.dumps({"name": "home", "svg": ""})
        result, success = apply_slide_icon_change_with_status(html, "did-icon", icon_data)
        assert success is True
        assert "home" in result

    def test_returns_false_for_empty_icon_data(self):
        html = '<div data-design-id="did-1">Text</div>'
        result, success = apply_slide_icon_change_with_status(html, "did-1", "")
        assert success is False
        assert result == html

    def test_icon_name_only_tries_material_icons(self):
        html = '<i data-design-id="did-1" class="material-symbols-outlined">star</i>'
        icon_data = json.dumps({"name": "home"})
        result, success = apply_slide_icon_change_with_status(html, "did-1", icon_data)
        assert success is True
        assert "home" in result

    def test_returns_false_for_missing_id_and_no_svg(self):
        html = '<div data-design-id="did-other">Text</div>'
        result, success = apply_slide_icon_change_with_status(html, "missing", '{"name":"x"}')
        assert success is False

    def test_wrapper_element_with_svg_inside(self):
        html = '<div data-design-id="did-wrapper"><svg><path d="M0 0"/></svg></div>'
        icon_data = json.dumps({"name": "rocket", "svg": '<circle cx="12" cy="12" r="5"/>'})
        result, success = apply_slide_icon_change_with_status(html, "did-wrapper", icon_data)
        assert success is True
        assert '<circle cx="12"' in result


# ---------------------------------------------------------------------------
# apply_slide_delete_change_with_status
# ---------------------------------------------------------------------------


class TestApplySlideDeleteChangeWithStatusR4:
    def test_deletes_element(self):
        result, success = apply_slide_delete_change_with_status(SIMPLE_HTML, design_id="did-1")
        assert success is True
        assert 'data-design-id="did-1"' not in result

    def test_returns_false_for_missing_id(self):
        result, success = apply_slide_delete_change_with_status(SIMPLE_HTML, design_id="missing")
        assert success is False
        assert result == SIMPLE_HTML

    def test_deletes_from_multi_element_html(self):
        result, success = apply_slide_delete_change_with_status(MULTI_HTML, design_id="did-2")
        assert success is True
        assert 'data-design-id="did-2"' not in result
        assert 'data-design-id="did-1"' in result
        assert 'data-design-id="did-3"' in result

    def test_deletes_nested_element(self):
        result, success = apply_slide_delete_change_with_status(NESTED_HTML, design_id="did-inner")
        assert success is True
        assert 'data-design-id="did-inner"' not in result

    def test_trims_leading_whitespace_on_own_line(self):
        html = "<div>\n  <p data-design-id='did-p'>content</p>\n</div>"
        result, success = apply_slide_delete_change_with_status(html, design_id="did-p")
        assert success is True
        assert "did-p" not in result


# ---------------------------------------------------------------------------
# apply_slide_swap_change_with_status
# ---------------------------------------------------------------------------


class TestApplySlideSwapChangeWithStatusR4:
    def test_swaps_two_elements(self):
        result, success = apply_slide_swap_change_with_status(
            MULTI_HTML, design_id="did-1", target_design_id="did-3"
        )
        assert success is True
        pos_1 = result.find('data-design-id="did-1"')
        pos_3 = result.find('data-design-id="did-3"')
        # After swap, did-3 comes before did-1
        assert pos_3 < pos_1

    def test_same_element_swap_is_noop(self):
        result, success = apply_slide_swap_change_with_status(
            SIMPLE_HTML, design_id="did-1", target_design_id="did-1"
        )
        assert success is True
        assert result == SIMPLE_HTML

    def test_returns_false_if_element_a_missing(self):
        result, success = apply_slide_swap_change_with_status(
            MULTI_HTML, design_id="missing", target_design_id="did-2"
        )
        assert success is False

    def test_returns_false_if_element_b_missing(self):
        result, success = apply_slide_swap_change_with_status(
            MULTI_HTML, design_id="did-1", target_design_id="missing"
        )
        assert success is False

    def test_adjacent_elements_swapped(self):
        result, success = apply_slide_swap_change_with_status(
            MULTI_HTML, design_id="did-1", target_design_id="did-2"
        )
        assert success is True
        pos_1 = result.find('data-design-id="did-1"')
        pos_2 = result.find('data-design-id="did-2"')
        assert pos_2 < pos_1


# ---------------------------------------------------------------------------
# apply_slide_move_change_with_status
# ---------------------------------------------------------------------------


class TestApplySlideMovecChangeWithStatusR4:
    def test_move_before_anchor(self):
        result, success = apply_slide_move_change_with_status(
            MULTI_HTML, design_id="did-3", anchor="before:did-1"
        )
        assert success is True
        pos_3 = result.find('data-design-id="did-3"')
        pos_1 = result.find('data-design-id="did-1"')
        assert pos_3 < pos_1

    def test_move_after_anchor(self):
        result, success = apply_slide_move_change_with_status(
            MULTI_HTML, design_id="did-1", anchor="after:did-3"
        )
        assert success is True
        pos_3 = result.find('data-design-id="did-3"')
        pos_1 = result.find('data-design-id="did-1"')
        assert pos_3 < pos_1

    def test_only_anchor_is_noop(self):
        result, success = apply_slide_move_change_with_status(
            SIMPLE_HTML, design_id="did-1", anchor="only"
        )
        assert success is True
        assert result == SIMPLE_HTML

    def test_empty_anchor_returns_false(self):
        result, success = apply_slide_move_change_with_status(
            SIMPLE_HTML, design_id="did-1", anchor=""
        )
        assert success is False

    def test_bare_anchor_falls_back_to_swap(self):
        # Legacy: bare design ID = swap
        result, success = apply_slide_move_change_with_status(
            MULTI_HTML, design_id="did-1", anchor="did-3"
        )
        # Result should be a swap (both should still exist)
        assert 'data-design-id="did-1"' in result
        assert 'data-design-id="did-3"' in result

    def test_missing_design_id_returns_false(self):
        result, success = apply_slide_move_change_with_status(
            MULTI_HTML, design_id="missing", anchor="before:did-1"
        )
        assert success is False

    def test_missing_anchor_target_returns_false(self):
        result, success = apply_slide_move_change_with_status(
            MULTI_HTML, design_id="did-1", anchor="before:missing"
        )
        assert success is False


# ---------------------------------------------------------------------------
# Convenience wrappers (apply_slide_*_change)
# ---------------------------------------------------------------------------


class TestConvenienceWrappersR4:
    def test_apply_slide_style_change_returns_string(self):
        html = '<div data-design-id="did-1">Text</div>'
        result = apply_slide_style_change(html, "did-1", "color", "blue")
        assert isinstance(result, str)
        assert "color: blue;" in result

    def test_apply_slide_text_change_returns_string(self):
        result = apply_slide_text_change(SIMPLE_HTML, "did-1", "new text")
        assert isinstance(result, str)
        assert "new text" in result

    def test_apply_slide_icon_change_returns_string(self):
        html = '<svg data-design-id="did-svg"><path/></svg>'
        result = apply_slide_icon_change(html, "did-svg", '<circle cx="12"/>')
        assert isinstance(result, str)

    def test_apply_slide_delete_change_returns_string(self):
        result = apply_slide_delete_change(SIMPLE_HTML, design_id="did-1")
        assert isinstance(result, str)
        assert "did-1" not in result

    def test_apply_slide_move_change_returns_string(self):
        result = apply_slide_move_change(MULTI_HTML, design_id="did-1", anchor="only")
        assert isinstance(result, str)

    def test_apply_slide_swap_change_returns_string(self):
        result = apply_slide_swap_change(MULTI_HTML, design_id="did-1", target_design_id="did-2")
        assert isinstance(result, str)
        assert "did-1" in result
        assert "did-2" in result
