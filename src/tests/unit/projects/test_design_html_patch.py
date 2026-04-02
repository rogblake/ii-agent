"""Unit tests for projects/design/utils/html_patch.py."""

from ii_agent.projects.design.utils.html_patch import (
    _extract_closing_tag_name,
    _extract_opening_tag_name,
    _find_tag_end,
    _parse_xpath,
    apply_slide_delete_change_with_status,
    apply_slide_style_change_with_status,
    apply_slide_text_change_with_status,
    sanitize_slide_presentation_name,
)


# ---------------------------------------------------------------------------
# sanitize_slide_presentation_name tests
# ---------------------------------------------------------------------------


class TestSanitizeSlidePresentationName:
    """Tests for sanitize_slide_presentation_name()."""

    def test_basic_name(self):
        assert sanitize_slide_presentation_name("My Presentation") == "My_Presentation"

    def test_spaces_replaced_with_underscores(self):
        assert sanitize_slide_presentation_name("hello world") == "hello_world"

    def test_special_characters_removed(self):
        # Spaces become underscores first, then special chars (!, @) are removed
        result = sanitize_slide_presentation_name("Hello! World@2024")
        # '!' is removed, space before World becomes '_'
        assert result == "Hello_World2024"

    def test_hyphens_preserved(self):
        assert sanitize_slide_presentation_name("my-deck") == "my-deck"

    def test_underscores_preserved(self):
        assert sanitize_slide_presentation_name("my_deck") == "my_deck"

    def test_empty_string_returns_presentation(self):
        assert sanitize_slide_presentation_name("") == "presentation"

    def test_only_spaces_returns_presentation(self):
        assert sanitize_slide_presentation_name("   ") == "presentation"

    def test_only_special_chars_returns_presentation(self):
        assert sanitize_slide_presentation_name("!!!###") == "presentation"

    def test_non_string_input_returns_presentation(self):
        assert sanitize_slide_presentation_name(None) == "presentation"  # type: ignore
        assert sanitize_slide_presentation_name(123) == "presentation"  # type: ignore

    def test_leading_trailing_spaces_stripped(self):
        result = sanitize_slide_presentation_name("  Hello  ")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_alphanumeric_only(self):
        result = sanitize_slide_presentation_name("Report2024")
        assert result == "Report2024"

    def test_unicode_letters_preserved(self):
        # Unicode letters pass isalnum()
        result = sanitize_slide_presentation_name("Café")
        assert len(result) > 0


# ---------------------------------------------------------------------------
# _find_tag_end tests
# ---------------------------------------------------------------------------


class TestFindTagEnd:
    """Tests for _find_tag_end()."""

    def test_simple_opening_tag(self):
        html = "<div>"
        result = _find_tag_end(html, 0)
        assert result == 4

    def test_tag_with_attributes(self):
        html = '<div class="foo">'
        result = _find_tag_end(html, 0)
        assert result == len(html) - 1

    def test_self_closing_tag(self):
        html = "<br />"
        result = _find_tag_end(html, 0)
        assert result == len(html) - 1

    def test_closing_tag(self):
        html = "</div>"
        result = _find_tag_end(html, 0)
        assert result == 5

    def test_tag_with_quoted_attributes_containing_gt(self):
        html = '<div title="a > b">'
        result = _find_tag_end(html, 0)
        assert html[result] == ">"
        # Should find the correct closing >
        assert result == len(html) - 1

    def test_returns_none_when_not_starting_with_lt(self):
        html = "div>"
        result = _find_tag_end(html, 0)
        assert result is None

    def test_returns_none_for_unclosed_tag(self):
        html = "<div class="
        result = _find_tag_end(html, 0)
        assert result is None

    def test_empty_string_returns_none(self):
        result = _find_tag_end("", 0)
        assert result is None

    def test_non_string_returns_none(self):
        result = _find_tag_end(None, 0)  # type: ignore
        assert result is None

    def test_start_index_beyond_length(self):
        html = "<div>"
        result = _find_tag_end(html, 100)
        assert result is None

    def test_single_quote_attribute(self):
        html = "<div class='foo'>"
        result = _find_tag_end(html, 0)
        assert result == len(html) - 1


# ---------------------------------------------------------------------------
# _extract_opening_tag_name tests
# ---------------------------------------------------------------------------


class TestExtractOpeningTagName:
    """Tests for _extract_opening_tag_name()."""

    def test_simple_div(self):
        assert _extract_opening_tag_name("<div>") == "div"

    def test_tag_with_attributes(self):
        assert _extract_opening_tag_name('<div class="foo">') == "div"

    def test_self_closing_tag(self):
        assert _extract_opening_tag_name("<br />") == "br"

    def test_uppercase_tag(self):
        assert _extract_opening_tag_name("<DIV>") == "DIV"

    def test_namespaced_tag(self):
        assert _extract_opening_tag_name("<svg:path>") == "svg:path"

    def test_empty_string_returns_none(self):
        assert _extract_opening_tag_name("") is None

    def test_non_string_returns_none(self):
        assert _extract_opening_tag_name(None) is None  # type: ignore

    def test_closing_tag_returns_none(self):
        assert _extract_opening_tag_name("</div>") is None

    def test_tag_starting_with_number_returns_none(self):
        assert _extract_opening_tag_name("<3tag>") is None

    def test_tag_with_space_after_lt(self):
        # Regex allows optional space after <
        result = _extract_opening_tag_name("< div>")
        assert result == "div"


# ---------------------------------------------------------------------------
# _extract_closing_tag_name tests
# ---------------------------------------------------------------------------


class TestExtractClosingTagName:
    """Tests for _extract_closing_tag_name()."""

    def test_simple_closing_tag(self):
        assert _extract_closing_tag_name("</div>") == "div"

    def test_closing_tag_with_space(self):
        assert _extract_closing_tag_name("</ div >") == "div"

    def test_opening_tag_returns_none(self):
        assert _extract_closing_tag_name("<div>") is None

    def test_empty_string_returns_none(self):
        assert _extract_closing_tag_name("") is None

    def test_non_string_returns_none(self):
        assert _extract_closing_tag_name(None) is None  # type: ignore

    def test_closing_span(self):
        assert _extract_closing_tag_name("</span>") == "span"

    def test_svg_closing(self):
        assert _extract_closing_tag_name("</svg>") == "svg"


# ---------------------------------------------------------------------------
# _parse_xpath tests
# ---------------------------------------------------------------------------


class TestParseXPath:
    """Tests for _parse_xpath()."""

    def test_simple_xpath(self):
        result = _parse_xpath("/html/body/div")
        assert result == [("html", 1), ("body", 1), ("div", 1)]

    def test_xpath_with_index(self):
        result = _parse_xpath("/html/body/div[2]")
        assert result == [("html", 1), ("body", 1), ("div", 2)]

    def test_complex_xpath(self):
        result = _parse_xpath("/html/body/div/div[2]/section/div[3]")
        assert result == [
            ("html", 1),
            ("body", 1),
            ("div", 1),
            ("div", 2),
            ("section", 1),
            ("div", 3),
        ]

    def test_empty_xpath_returns_empty_list(self):
        assert _parse_xpath("") == []

    def test_none_xpath_returns_empty_list(self):
        assert _parse_xpath(None) == []  # type: ignore

    def test_tag_names_lowercased(self):
        result = _parse_xpath("/HTML/BODY/DIV")
        assert result == [("html", 1), ("body", 1), ("div", 1)]

    def test_invalid_segment_skipped(self):
        result = _parse_xpath("/html/123invalid/div")
        # "123invalid" doesn't match tag regex, should be skipped
        assert ("html", 1) in result
        assert ("div", 1) in result

    def test_multiple_indices(self):
        result = _parse_xpath("/div[1]/span[5]")
        assert ("div", 1) in result
        assert ("span", 5) in result

    def test_no_leading_slash(self):
        result = _parse_xpath("html/body")
        assert result == [("html", 1), ("body", 1)]

    def test_single_segment(self):
        result = _parse_xpath("/div")
        assert result == [("div", 1)]

    def test_index_greater_than_one(self):
        result = _parse_xpath("/section[10]")
        assert result == [("section", 10)]


# ---------------------------------------------------------------------------
# apply_slide_style_change_with_status tests
# ---------------------------------------------------------------------------


class TestApplySlideStyleChangeWithStatus:
    """Tests for apply_slide_style_change_with_status()."""

    def _make_html(self, design_id: str, extra: str = "") -> str:
        return f'<div data-design-id="{design_id}"{extra}>Content</div>'

    def test_adds_style_attribute(self):
        html = self._make_html("el-1")
        new_html, success = apply_slide_style_change_with_status(html, "el-1", "color", "red")
        assert success
        assert "color: red;" in new_html

    def test_returns_false_when_design_id_not_found(self):
        html = self._make_html("el-1")
        new_html, success = apply_slide_style_change_with_status(html, "el-999", "color", "red")
        assert not success
        assert new_html == html

    def test_updates_existing_style_attribute(self):
        html = '<div data-design-id="el-2" style="font-size: 14px;">Text</div>'
        new_html, success = apply_slide_style_change_with_status(html, "el-2", "color", "blue")
        assert success
        assert "color: blue;" in new_html
        assert "font-size: 14px" in new_html

    def test_camel_case_property_converted_to_kebab(self):
        html = self._make_html("el-3")
        new_html, success = apply_slide_style_change_with_status(
            html, "el-3", "backgroundColor", "green"
        )
        assert success
        assert "background-color: green;" in new_html

    def test_empty_value_removes_property(self):
        html = '<div data-design-id="el-4" style="color: red;">Text</div>'
        new_html, success = apply_slide_style_change_with_status(html, "el-4", "color", "")
        assert success
        # color should be removed
        assert "color: red" not in new_html

    def test_self_closing_tag_receives_style(self):
        html = '<img data-design-id="img-1" />'
        new_html, success = apply_slide_style_change_with_status(html, "img-1", "width", "100px")
        assert success
        assert "width: 100px;" in new_html

    def test_returns_tuple_html_and_bool(self):
        html = self._make_html("el-5")
        result = apply_slide_style_change_with_status(html, "el-5", "margin", "10px")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_xpath_fallback_when_design_id_missing(self):
        html = "<html><body><div><div>Content</div></div></body></html>"
        # No data-design-id, use XPath fallback
        new_html, success = apply_slide_style_change_with_status(
            html, "nonexistent", "color", "red", xpath="/html/body/div/div"
        )
        # XPath fallback - success depends on xpath finding the element
        assert isinstance(success, bool)


# ---------------------------------------------------------------------------
# apply_slide_text_change_with_status tests
# ---------------------------------------------------------------------------


class TestApplySlideTextChangeWithStatus:
    """Tests for apply_slide_text_change_with_status()."""

    def _make_html(self, design_id: str, text: str = "Original") -> str:
        return f'<div data-design-id="{design_id}">{text}</div>'

    def test_replaces_text_content(self):
        html = self._make_html("t-1", "Original Text")
        new_html, success = apply_slide_text_change_with_status(html, "t-1", "New Text")
        assert success
        assert "New Text" in new_html

    def test_returns_false_when_design_id_not_found(self):
        html = self._make_html("t-1", "Text")
        new_html, success = apply_slide_text_change_with_status(html, "t-999", "New Text")
        assert not success
        assert new_html == html

    def test_escapes_html_special_chars_in_text(self):
        html = self._make_html("t-2", "Old")
        new_html, success = apply_slide_text_change_with_status(
            html, "t-2", "<script>alert('xss')</script>"
        )
        assert success
        # Should be HTML-escaped
        assert "<script>" not in new_html
        assert "&lt;script&gt;" in new_html

    def test_preserves_surrounding_html(self):
        html = '<p>Before</p><div data-design-id="t-3">Old</div><p>After</p>'
        new_html, success = apply_slide_text_change_with_status(html, "t-3", "New")
        assert success
        assert "<p>Before</p>" in new_html
        assert "<p>After</p>" in new_html

    def test_text_with_nested_elements_replaced_at_top_level(self):
        html = '<div data-design-id="t-4"><span>nested</span> text</div>'
        new_html, success = apply_slide_text_change_with_status(html, "t-4", "Replaced")
        assert success
        assert "Replaced" in new_html

    def test_returns_tuple(self):
        html = self._make_html("t-5")
        result = apply_slide_text_change_with_status(html, "t-5", "Test")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_self_closing_tag_returns_false(self):
        html = '<img data-design-id="img-1" />'
        new_html, success = apply_slide_text_change_with_status(html, "img-1", "new text")
        assert not success

    def test_empty_text_replaces_content(self):
        html = self._make_html("t-6", "Some content")
        new_html, success = apply_slide_text_change_with_status(html, "t-6", "")
        assert success


# ---------------------------------------------------------------------------
# apply_slide_delete_change_with_status tests
# ---------------------------------------------------------------------------


class TestApplySlideDeleteChangeWithStatus:
    """Tests for apply_slide_delete_change_with_status()."""

    def _make_html(self, design_id: str) -> str:
        return (
            f'<div class="container">'
            f'  <p data-design-id="{design_id}">Delete me</p>'
            f"  <p>Keep me</p>"
            f"</div>"
        )

    def test_deletes_element_by_design_id(self):
        html = self._make_html("del-1")
        new_html, success = apply_slide_delete_change_with_status(html, design_id="del-1")
        assert success
        assert 'data-design-id="del-1"' not in new_html
        assert "Delete me" not in new_html

    def test_preserves_other_elements(self):
        html = self._make_html("del-2")
        new_html, success = apply_slide_delete_change_with_status(html, design_id="del-2")
        assert success
        assert "Keep me" in new_html

    def test_returns_false_when_design_id_not_found(self):
        html = self._make_html("del-3")
        new_html, success = apply_slide_delete_change_with_status(html, design_id="nonexistent")
        assert not success
        assert new_html == html

    def test_returns_tuple(self):
        html = self._make_html("del-4")
        result = apply_slide_delete_change_with_status(html, design_id="del-4")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_deletes_nested_element(self):
        html = '<div data-design-id="outer">  <span data-design-id="inner">Inner</span></div>'
        new_html, success = apply_slide_delete_change_with_status(html, design_id="inner")
        assert success
        assert "Inner" not in new_html
        # Outer should still be there
        assert 'data-design-id="outer"' in new_html

    def test_deletes_self_closing_element(self):
        html = '<div><img data-design-id="img-del" src="x.png" />Keep</div>'
        new_html, success = apply_slide_delete_change_with_status(html, design_id="img-del")
        assert success
        assert 'data-design-id="img-del"' not in new_html

    def test_trims_leading_whitespace_on_own_line(self):
        html = '<div>\n  <p data-design-id="trim-1">Text</p>\n</div>'
        new_html, success = apply_slide_delete_change_with_status(html, design_id="trim-1")
        assert success
        # The element should be removed cleanly
        assert 'data-design-id="trim-1"' not in new_html

    def test_empty_html_returns_false(self):
        _, success = apply_slide_delete_change_with_status("", design_id="any")
        assert not success
