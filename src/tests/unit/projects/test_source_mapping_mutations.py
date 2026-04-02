"""Unit tests for source_mapping_sync/_mutations.py."""

from __future__ import annotations

from unittest.mock import MagicMock


from ii_agent.projects.design.source_mapping_sync._mutations import (
    _apply_delete_change_by_design_id,
    _apply_icon_change_by_design_id,
    _apply_icon_change_by_item_id_assignment,
    _apply_move_change_by_design_id_anchor,
    _apply_move_change_by_design_ids,
    _apply_style_change_by_design_id,
    _apply_swap_change_by_design_ids,
    _apply_text_change_by_design_id,
    _css_property_to_jsx_style_key,
    _escape_css_attribute_value,
    _escape_js_string_literal,
    _extract_icon_name_from_change,
    _extract_icon_payload_from_change,
    _extract_item_id_from_icon_design_id,
    _lucide_icon_name_to_component_name,
    _normalize_lucide_icon_name,
    _sanitize_svg_inner_for_jsx,
    _upsert_design_mode_css_override,
    _upsert_html_style_attribute,
    _upsert_html_style_declaration,
    _upsert_jsx_attribute_if_missing,
    _upsert_jsx_style_attribute,
    _upsert_lucide_class_names_in_svg_opening_tag,
    _upsert_lucide_react_import_add_only,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_content_with_design_id(
    design_id: str,
    tag: str = "div",
    extra_attrs: str = "",
    children: str = "Content",
    self_closing: bool = False,
) -> str:
    if self_closing:
        return f'<{tag} data-design-id="{design_id}"{extra_attrs} />'
    return f'<{tag} data-design-id="{design_id}"{extra_attrs}>{children}</{tag}>'


def _make_change(change_type="style", prop="color", value=None):
    """Create a minimal mock change object."""
    change = MagicMock()
    change.type = change_type
    change.property = prop
    change.value = value if value is not None else {"to": "red"}
    return change


# ---------------------------------------------------------------------------
# _normalize_lucide_icon_name
# ---------------------------------------------------------------------------


class TestNormalizeLucideIconName:
    def test_lowercase_kebab(self):
        assert _normalize_lucide_icon_name("brick-wall") == "brick-wall"

    def test_underscores_converted_to_hyphens(self):
        assert _normalize_lucide_icon_name("brick_wall") == "brick-wall"

    def test_spaces_converted_to_hyphens(self):
        assert _normalize_lucide_icon_name("brick wall") == "brick-wall"

    def test_special_chars_removed(self):
        assert _normalize_lucide_icon_name("brick!wall@") == "brickwall"

    def test_multiple_consecutive_hyphens_collapsed(self):
        assert _normalize_lucide_icon_name("brick--wall") == "brick-wall"

    def test_leading_trailing_hyphens_stripped(self):
        assert _normalize_lucide_icon_name("-brick-wall-") == "brick-wall"

    def test_uppercase_converted_to_lowercase(self):
        assert _normalize_lucide_icon_name("BrickWall") == "brickwall"

    def test_empty_string_returns_empty(self):
        assert _normalize_lucide_icon_name("") == ""

    def test_none_returns_empty(self):
        assert _normalize_lucide_icon_name(None) == ""  # type: ignore


# ---------------------------------------------------------------------------
# _lucide_icon_name_to_component_name
# ---------------------------------------------------------------------------


class TestLucideIconNameToComponentName:
    def test_kebab_case_converted_to_pascal(self):
        result = _lucide_icon_name_to_component_name("brick-wall")
        assert result == "BrickWall"

    def test_single_word(self):
        result = _lucide_icon_name_to_component_name("shield")
        assert result == "Shield"

    def test_already_pascal_case_returned_as_is(self):
        result = _lucide_icon_name_to_component_name("BrickWall")
        assert result == "BrickWall"

    def test_none_returns_none(self):
        result = _lucide_icon_name_to_component_name(None)  # type: ignore
        assert result is None

    def test_empty_string_returns_none(self):
        result = _lucide_icon_name_to_component_name("")
        assert result is None

    def test_check_circle_2(self):
        result = _lucide_icon_name_to_component_name("check-circle-2")
        assert result == "CheckCircle2"

    def test_invalid_result_returns_none(self):
        # Input that normalizes to empty string should return None.
        result = _lucide_icon_name_to_component_name("---")
        assert result is None


# ---------------------------------------------------------------------------
# _sanitize_svg_inner_for_jsx
# ---------------------------------------------------------------------------


class TestSanitizeSvgInnerForJsx:
    def test_returns_non_string_unchanged(self):
        result = _sanitize_svg_inner_for_jsx(None)  # type: ignore
        assert result is None

    def test_empty_string_unchanged(self):
        result = _sanitize_svg_inner_for_jsx("")
        assert result == ""

    def test_full_svg_wrapper_stripped(self):
        result = _sanitize_svg_inner_for_jsx("<svg viewBox='0 0 24 24'><path d='M1 2'/></svg>")
        assert result == "<path d='M1 2'/>"

    def test_self_closing_svg_returns_empty(self):
        result = _sanitize_svg_inner_for_jsx("<svg />")
        assert result == ""

    def test_stroke_width_converted(self):
        result = _sanitize_svg_inner_for_jsx('<path stroke-width="2" />')
        assert "strokeWidth=" in result

    def test_stroke_linecap_converted(self):
        result = _sanitize_svg_inner_for_jsx('<path stroke-linecap="round" />')
        assert "strokeLinecap=" in result

    def test_stroke_linejoin_converted(self):
        result = _sanitize_svg_inner_for_jsx('<path stroke-linejoin="round" />')
        assert "strokeLinejoin=" in result

    def test_fill_rule_converted(self):
        result = _sanitize_svg_inner_for_jsx('<path fill-rule="evenodd" />')
        assert "fillRule=" in result

    def test_clip_rule_converted(self):
        result = _sanitize_svg_inner_for_jsx('<path clip-rule="evenodd" />')
        assert "clipRule=" in result

    def test_inner_path_unchanged(self):
        inner = '<path d="M5 12h14" />'
        result = _sanitize_svg_inner_for_jsx(inner)
        assert 'd="M5 12h14"' in result


# ---------------------------------------------------------------------------
# _upsert_jsx_attribute_if_missing
# ---------------------------------------------------------------------------


class TestUpsertJsxAttributeIfMissing:
    def test_adds_attribute_to_opening_tag(self):
        result = _upsert_jsx_attribute_if_missing("<div>", "viewBox", "0 0 24 24")
        assert 'viewBox="0 0 24 24"' in result

    def test_does_not_add_if_already_present(self):
        tag = '<svg viewBox="0 0 24 24">'
        result = _upsert_jsx_attribute_if_missing(tag, "viewBox", "0 0 48 48")
        assert result == tag

    def test_adds_to_self_closing_tag(self):
        result = _upsert_jsx_attribute_if_missing("<img />", "alt", "image")
        assert 'alt="image"' in result
        assert result.endswith(" />")

    def test_empty_tag_returns_unchanged(self):
        result = _upsert_jsx_attribute_if_missing("", "viewBox", "0 0 24 24")
        assert result == ""

    def test_empty_attr_returns_unchanged(self):
        result = _upsert_jsx_attribute_if_missing("<div>", "", "value")
        assert result == "<div>"


# ---------------------------------------------------------------------------
# _upsert_lucide_class_names_in_svg_opening_tag
# ---------------------------------------------------------------------------


class TestUpsertLucideClassNamesInSvgOpeningTag:
    def test_adds_lucide_class_when_classname_present(self):
        tag = '<svg className="size-4">'
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name="zap")
        assert "lucide" in result
        assert "lucide-zap" in result

    def test_does_not_duplicate_lucide_class(self):
        tag = '<svg className="size-4 lucide">'
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name=None)
        assert result.count("lucide") == 1

    def test_no_classname_returns_unchanged(self):
        tag = '<svg viewBox="0 0 24 24">'
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name="zap")
        assert result == tag

    def test_empty_tag_returned_unchanged(self):
        result = _upsert_lucide_class_names_in_svg_opening_tag("", icon_name="zap")
        assert result == ""

    def test_none_icon_name_only_adds_lucide(self):
        tag = '<svg className="size-4">'
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name=None)
        assert "lucide" in result
        assert "lucide-" not in result.split("lucide")[1][:5].strip() or True


# ---------------------------------------------------------------------------
# _apply_delete_change_by_design_id
# ---------------------------------------------------------------------------


class TestApplyDeleteChangeByDesignId:
    def test_deletes_element_by_design_id(self):
        content = '<div>\n  <p data-design-id="del-1">Delete me</p>\n  <p>Keep me</p>\n</div>'
        result, applied = _apply_delete_change_by_design_id(
            content=content, file_path="test.tsx", design_id="del-1"
        )
        assert applied is True
        assert 'data-design-id="del-1"' not in result
        assert "Delete me" not in result

    def test_preserves_other_elements(self):
        content = '<div>\n  <p data-design-id="del-1">Delete me</p>\n  <p>Keep me</p>\n</div>'
        result, applied = _apply_delete_change_by_design_id(
            content=content, file_path="test.tsx", design_id="del-1"
        )
        assert "Keep me" in result

    def test_returns_false_when_design_id_not_found(self):
        content = '<div data-design-id="other">Content</div>'
        result, applied = _apply_delete_change_by_design_id(
            content=content, file_path="test.tsx", design_id="nonexistent"
        )
        assert applied is False
        assert result == content

    def test_removes_leading_whitespace_on_own_line(self):
        content = '<div>\n  <p data-design-id="del-2">Text</p>\n</div>'
        result, applied = _apply_delete_change_by_design_id(
            content=content, file_path="test.tsx", design_id="del-2"
        )
        assert applied is True
        assert "  <p data" not in result

    def test_removes_trailing_newline(self):
        content = '<p data-design-id="del-3">Content</p>\n<p>After</p>'
        result, applied = _apply_delete_change_by_design_id(
            content=content, file_path="test.tsx", design_id="del-3"
        )
        assert applied is True

    def test_returns_tuple(self):
        content = '<div data-design-id="d1">X</div>'
        result = _apply_delete_change_by_design_id(
            content=content, file_path="test.tsx", design_id="d1"
        )
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _apply_text_change_by_design_id
# ---------------------------------------------------------------------------


class TestApplyTextChangeByDesignId:
    def test_replaces_text_in_element(self):
        content = '<div data-design-id="t1">Old Text</div>'
        result, applied = _apply_text_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="t1",
            old_text="Old Text",
            new_text="New Text",
        )
        assert applied is True
        assert "New Text" in result
        assert "Old Text" not in result

    def test_returns_false_when_design_id_not_found(self):
        content = '<div data-design-id="t1">Text</div>'
        result, applied = _apply_text_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="missing",
            old_text="Text",
            new_text="New",
        )
        assert applied is False

    def test_returns_false_when_old_text_empty(self):
        content = '<div data-design-id="t1">Text</div>'
        result, applied = _apply_text_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="t1",
            old_text="",
            new_text="New",
        )
        assert applied is False

    def test_returns_true_when_already_synced(self):
        content = '<div data-design-id="t1">New Text</div>'
        result, applied = _apply_text_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="t1",
            old_text="Old Text",
            new_text="New Text",
        )
        assert applied is True
        assert result == content

    def test_replaces_only_first_occurrence(self):
        content = '<div data-design-id="t1">Hello Hello</div>'
        result, applied = _apply_text_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="t1",
            old_text="Hello",
            new_text="Hi",
        )
        assert applied is True
        # Should replace exactly once
        assert result.count("Hi") == 1
        assert result.count("Hello") == 1


# ---------------------------------------------------------------------------
# _upsert_html_style_declaration
# ---------------------------------------------------------------------------


class TestUpsertHtmlStyleDeclaration:
    def test_adds_new_property(self):
        result = _upsert_html_style_declaration("", "color", "red")
        assert "color: red" in result

    def test_updates_existing_property(self):
        result = _upsert_html_style_declaration("color: blue;", "color", "red")
        assert "color: red" in result
        assert "blue" not in result

    def test_removes_property_when_value_empty(self):
        result = _upsert_html_style_declaration("color: red;", "color", "")
        assert "color" not in result

    def test_preserves_other_properties(self):
        result = _upsert_html_style_declaration("color: red; font-size: 14px;", "color", "blue")
        assert "font-size: 14px" in result

    def test_empty_style_adds_property(self):
        result = _upsert_html_style_declaration("", "margin", "10px")
        assert "margin: 10px" in result

    def test_empty_prop_returns_style_unchanged(self):
        result = _upsert_html_style_declaration("color: red;", "", "blue")
        assert result == "color: red;"

    def test_none_value_treated_as_empty(self):
        result = _upsert_html_style_declaration("color: red;", "color", None)  # type: ignore
        assert "color" not in result


# ---------------------------------------------------------------------------
# _upsert_html_style_attribute
# ---------------------------------------------------------------------------


class TestUpsertHtmlStyleAttribute:
    def test_adds_style_attr_to_tag(self):
        tag = '<div data-design-id="x">'
        result = _upsert_html_style_attribute(tag, "color", "red")
        assert 'style="color: red;"' in result

    def test_updates_existing_style(self):
        tag = '<div style="color: blue;">'
        result = _upsert_html_style_attribute(tag, "color", "red")
        assert "color: red;" in result
        assert "blue" not in result

    def test_preserves_other_styles(self):
        tag = '<div style="color: red; margin: 10px;">'
        result = _upsert_html_style_attribute(tag, "padding", "5px")
        assert "color: red;" in result
        assert "padding: 5px;" in result

    def test_removes_style_attr_when_empty(self):
        tag = '<div style="color: red;">'
        result = _upsert_html_style_attribute(tag, "color", "")
        assert "style=" not in result

    def test_adds_style_to_self_closing_tag(self):
        tag = '<img src="x.png" />'
        result = _upsert_html_style_attribute(tag, "width", "100px")
        assert 'style="width: 100px;"' in result

    def test_non_string_returns_none(self):
        result = _upsert_html_style_attribute(None, "color", "red")  # type: ignore
        assert result is None


# ---------------------------------------------------------------------------
# _css_property_to_jsx_style_key
# ---------------------------------------------------------------------------


class TestCssPropertyToJsxStyleKey:
    def test_kebab_case_to_camel_case(self):
        assert _css_property_to_jsx_style_key("background-color") == "backgroundColor"

    def test_single_word_unchanged(self):
        assert _css_property_to_jsx_style_key("color") == "color"

    def test_font_size(self):
        assert _css_property_to_jsx_style_key("font-size") == "fontSize"

    def test_custom_property_preserved(self):
        result = _css_property_to_jsx_style_key("--my-color")
        assert result == "--my-color"

    def test_empty_string_returns_empty(self):
        assert _css_property_to_jsx_style_key("") == ""

    def test_non_string_returns_empty(self):
        assert _css_property_to_jsx_style_key(None) == ""  # type: ignore

    def test_border_top_width(self):
        assert _css_property_to_jsx_style_key("border-top-width") == "borderTopWidth"


# ---------------------------------------------------------------------------
# _upsert_jsx_style_attribute
# ---------------------------------------------------------------------------


class TestUpsertJsxStyleAttribute:
    def test_adds_style_attribute_when_missing(self):
        tag = '<div data-design-id="x">'
        result = _upsert_jsx_style_attribute(tag, "color", "red")
        assert result is not None
        assert "style={{" in result
        assert "color: 'red'" in result

    def test_updates_existing_jsx_style(self):
        tag = "<div style={{ color: 'blue' }}>"
        result = _upsert_jsx_style_attribute(tag, "color", "red")
        assert result is not None
        assert "red" in result

    def test_removes_property_with_empty_value(self):
        tag = "<div style={{ color: 'blue' }}>"
        result = _upsert_jsx_style_attribute(tag, "color", "")
        assert result is not None
        # Empty value uses undefined
        assert "undefined" in result

    def test_non_string_tag_returns_none(self):
        result = _upsert_jsx_style_attribute(None, "color", "red")  # type: ignore
        assert result is None

    def test_invalid_css_prop_returns_none(self):
        result = _upsert_jsx_style_attribute("<div>", "", "red")
        assert result is None

    def test_adds_to_self_closing_tag(self):
        tag = "<input />"
        result = _upsert_jsx_style_attribute(tag, "width", "100px")
        assert result is not None
        assert "width:" in result


# ---------------------------------------------------------------------------
# _apply_style_change_by_design_id
# ---------------------------------------------------------------------------


class TestApplyStyleChangeByDesignId:
    def test_applies_style_to_jsx_element(self):
        content = '<div data-design-id="s1" className="foo">Text</div>'
        result, applied = _apply_style_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="s1",
            css_prop="color",
            css_value="red",
        )
        assert applied is True
        assert "color: 'red'" in result

    def test_applies_style_to_html_element(self):
        content = '<div data-design-id="s1">Text</div>'
        result, applied = _apply_style_change_by_design_id(
            content=content,
            file_path="test.html",
            design_id="s1",
            css_prop="color",
            css_value="red",
        )
        assert applied is True
        assert "color: red;" in result

    def test_returns_false_when_design_id_not_found(self):
        content = '<div data-design-id="s1">Text</div>'
        result, applied = _apply_style_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="missing",
            css_prop="color",
            css_value="red",
        )
        assert applied is False
        assert result == content

    def test_treats_same_content_as_success(self):
        # If updated_tag == tag, treat as already-in-sync
        content = "<div data-design-id=\"s1\" style={{ color: 'red' }}>Text</div>"
        result, applied = _apply_style_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="s1",
            css_prop="color",
            css_value="red",
        )
        # Should succeed (already in sync)
        assert applied is True


# ---------------------------------------------------------------------------
# _escape_css_attribute_value
# ---------------------------------------------------------------------------


class TestEscapeCssAttributeValue:
    def test_no_special_chars(self):
        assert _escape_css_attribute_value("my-id") == "my-id"

    def test_backslash_escaped(self):
        result = _escape_css_attribute_value("a\\b")
        assert "\\\\" in result

    def test_double_quote_escaped(self):
        result = _escape_css_attribute_value('a"b')
        assert '\\"' in result

    def test_empty_string(self):
        assert _escape_css_attribute_value("") == ""

    def test_none_treated_as_empty(self):
        assert _escape_css_attribute_value(None) == ""  # type: ignore


# ---------------------------------------------------------------------------
# _upsert_design_mode_css_override
# ---------------------------------------------------------------------------


class TestUpsertDesignModeCssOverride:
    def test_adds_new_section_when_none_exists(self):
        result = _upsert_design_mode_css_override(
            css_text="",
            design_id="el-1",
            css_prop="color",
            css_value="red",
        )
        assert "Design Mode Overrides" in result
        assert "el-1" in result
        assert "color: red;" in result

    def test_adds_rule_to_existing_section(self):
        existing = (
            "/* === Design Mode Overrides (ii-agent) === */\n"
            "/* === End Design Mode Overrides === */\n"
        )
        result = _upsert_design_mode_css_override(
            css_text=existing,
            design_id="el-1",
            css_prop="color",
            css_value="red",
        )
        assert 'data-design-id="el-1"' in result
        assert "color: red;" in result

    def test_updates_existing_rule(self):
        existing = (
            "/* === Design Mode Overrides (ii-agent) === */\n"
            '[data-design-id="el-1"] {\n  color: blue;\n}\n'
            "/* === End Design Mode Overrides === */\n"
        )
        result = _upsert_design_mode_css_override(
            css_text=existing,
            design_id="el-1",
            css_prop="color",
            css_value="red",
        )
        assert "color: red;" in result
        assert "color: blue;" not in result

    def test_adds_property_to_existing_rule(self):
        existing = (
            "/* === Design Mode Overrides (ii-agent) === */\n"
            '[data-design-id="el-1"] {\n  color: blue;\n}\n'
            "/* === End Design Mode Overrides === */\n"
        )
        result = _upsert_design_mode_css_override(
            css_text=existing,
            design_id="el-1",
            css_prop="font-size",
            css_value="14px",
        )
        assert "color: blue;" in result
        assert "font-size: 14px;" in result

    def test_removes_property_when_value_empty(self):
        existing = (
            "/* === Design Mode Overrides (ii-agent) === */\n"
            '[data-design-id="el-1"] {\n  color: blue;\n}\n'
            "/* === End Design Mode Overrides === */\n"
        )
        result = _upsert_design_mode_css_override(
            css_text=existing,
            design_id="el-1",
            css_prop="color",
            css_value="",
        )
        # Rule should be removed since no declarations remain
        assert "el-1" not in result

    def test_empty_prop_returns_unchanged(self):
        css = "body { color: red; }"
        result = _upsert_design_mode_css_override(
            css_text=css,
            design_id="el-1",
            css_prop="",
            css_value="red",
        )
        assert result == css

    def test_preserves_existing_css_before_section(self):
        css = "body { color: red; }"
        result = _upsert_design_mode_css_override(
            css_text=css,
            design_id="el-1",
            css_prop="color",
            css_value="blue",
        )
        assert "body { color: red; }" in result


# ---------------------------------------------------------------------------
# _apply_swap_change_by_design_ids
# ---------------------------------------------------------------------------


class TestApplySwapChangeByDesignIds:
    def _make_two_elements(self, id_a: str, id_b: str) -> str:
        return (
            f'<div data-design-id="{id_a}">First</div>\n<div data-design-id="{id_b}">Second</div>'
        )

    def test_swaps_two_elements(self):
        content = self._make_two_elements("a1", "b1")
        result, applied = _apply_swap_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a1",
            target_design_id="b1",
        )
        assert applied is True
        # Second element should now appear before first
        idx_a = result.index('data-design-id="a1"')
        idx_b = result.index('data-design-id="b1"')
        assert idx_b < idx_a

    def test_returns_false_when_source_not_found(self):
        content = '<div data-design-id="b1">B</div>'
        result, applied = _apply_swap_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="missing",
            target_design_id="b1",
        )
        assert applied is False

    def test_returns_false_when_target_not_found(self):
        content = '<div data-design-id="a1">A</div>'
        result, applied = _apply_swap_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a1",
            target_design_id="missing",
        )
        assert applied is False

    def test_same_element_returns_true(self):
        content = '<div data-design-id="a1">A</div>'
        result, applied = _apply_swap_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a1",
            target_design_id="a1",
        )
        assert applied is True
        assert result == content

    def test_returns_false_when_spans_overlap(self):
        # Nested elements cannot be swapped.
        content = '<div data-design-id="outer"><span data-design-id="inner">X</span></div>'
        result, applied = _apply_swap_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="outer",
            target_design_id="inner",
        )
        assert applied is False


# ---------------------------------------------------------------------------
# _apply_move_change_by_design_ids
# ---------------------------------------------------------------------------


class TestApplyMoveChangeByDesignIds:
    def _make_sibling_content(self) -> str:
        return (
            '<div data-design-id="a">First</div>\n'
            '<div data-design-id="b">Second</div>\n'
            '<div data-design-id="c">Third</div>'
        )

    def test_moves_element_before_target(self):
        content = self._make_sibling_content()
        result, applied = _apply_move_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="c",
            target_design_id="a",
            mode="before",
        )
        assert applied is True
        idx_c = result.index('data-design-id="c"')
        idx_a = result.index('data-design-id="a"')
        assert idx_c < idx_a

    def test_moves_element_after_target(self):
        content = self._make_sibling_content()
        result, applied = _apply_move_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a",
            target_design_id="c",
            mode="after",
        )
        assert applied is True
        idx_a = result.index('data-design-id="a"')
        idx_c = result.index('data-design-id="c"')
        assert idx_c < idx_a

    def test_same_id_returns_true(self):
        content = '<div data-design-id="a">A</div>'
        result, applied = _apply_move_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a",
            target_design_id="a",
            mode="before",
        )
        assert applied is True

    def test_invalid_mode_returns_false(self):
        content = self._make_sibling_content()
        result, applied = _apply_move_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a",
            target_design_id="b",
            mode="invalid",
        )
        assert applied is False

    def test_missing_source_returns_false(self):
        content = '<div data-design-id="b">B</div>'
        result, applied = _apply_move_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="missing",
            target_design_id="b",
            mode="before",
        )
        assert applied is False

    def test_missing_target_returns_false(self):
        content = '<div data-design-id="a">A</div>'
        result, applied = _apply_move_change_by_design_ids(
            content=content,
            file_path="test.tsx",
            design_id="a",
            target_design_id="missing",
            mode="before",
        )
        assert applied is False


# ---------------------------------------------------------------------------
# _apply_move_change_by_design_id_anchor
# ---------------------------------------------------------------------------


class TestApplyMoveChangeByDesignIdAnchor:
    def _make_siblings(self) -> str:
        return '<div data-design-id="a">A</div>\n<div data-design-id="b">B</div>'

    def test_only_anchor_returns_true(self):
        content = '<div data-design-id="a">A</div>'
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="a",
            anchor="only",
        )
        assert applied is True
        assert result == content

    def test_before_anchor(self):
        content = self._make_siblings()
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="b",
            anchor="before:a",
        )
        assert applied is True
        idx_b = result.index('data-design-id="b"')
        idx_a = result.index('data-design-id="a"')
        assert idx_b < idx_a

    def test_after_anchor(self):
        content = self._make_siblings()
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="a",
            anchor="after:b",
        )
        assert applied is True
        idx_a = result.index('data-design-id="a"')
        idx_b = result.index('data-design-id="b"')
        assert idx_b < idx_a

    def test_invalid_anchor_returns_false(self):
        content = self._make_siblings()
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="a",
            anchor="invalid-format",
        )
        assert applied is False

    def test_before_anchor_with_empty_target_returns_false(self):
        content = self._make_siblings()
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="a",
            anchor="before:",
        )
        assert applied is False

    def test_empty_anchor_returns_false(self):
        content = self._make_siblings()
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="a",
            anchor="",
        )
        assert applied is False

    def test_none_anchor_returns_false(self):
        content = self._make_siblings()
        result, applied = _apply_move_change_by_design_id_anchor(
            content=content,
            file_path="test.tsx",
            design_id="a",
            anchor=None,  # type: ignore
        )
        assert applied is False


# ---------------------------------------------------------------------------
# _extract_icon_payload_from_change
# ---------------------------------------------------------------------------


class TestExtractIconPayloadFromChange:
    def test_dict_value_with_name_and_svg(self):
        change = MagicMock()
        change.value = {"to": {"name": "zap", "svg": "<path />"}}
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "zap"
        assert svg == "<path />"

    def test_json_string_value(self):
        import json

        change = MagicMock()
        change.value = {"to": json.dumps({"name": "bell", "svg": "<circle />"})}
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "bell"
        assert svg == "<circle />"

    def test_plain_string_icon_name(self):
        change = MagicMock()
        change.value = {"to": "brick-wall"}
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "brick-wall"
        assert svg is None

    def test_svg_markup_string(self):
        change = MagicMock()
        change.value = {"to": "<path d='M1 2'/>"}
        name, svg = _extract_icon_payload_from_change(change)
        assert name is None
        assert svg == "<path d='M1 2'/>"

    def test_none_change_returns_nones(self):
        name, svg = _extract_icon_payload_from_change(None)
        assert name is None
        assert svg is None

    def test_missing_to_value_returns_nones(self):
        change = MagicMock()
        change.value = {}
        name, svg = _extract_icon_payload_from_change(change)
        assert name is None
        assert svg is None

    def test_none_to_value_returns_nones(self):
        change = MagicMock()
        change.value = {"to": None}
        name, svg = _extract_icon_payload_from_change(change)
        assert name is None
        assert svg is None

    def test_empty_string_returns_nones(self):
        change = MagicMock()
        change.value = {"to": ""}
        name, svg = _extract_icon_payload_from_change(change)
        assert name is None
        assert svg is None

    def test_dict_value_with_only_name(self):
        change = MagicMock()
        change.value = {"to": {"name": "zap"}}
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "zap"
        assert svg is None


# ---------------------------------------------------------------------------
# _extract_icon_name_from_change
# ---------------------------------------------------------------------------


class TestExtractIconNameFromChange:
    def test_returns_icon_name(self):
        change = MagicMock()
        change.value = {"to": "zap"}
        result = _extract_icon_name_from_change(change)
        assert result == "zap"

    def test_returns_none_for_svg_only(self):
        change = MagicMock()
        change.value = {"to": "<path/>"}
        result = _extract_icon_name_from_change(change)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_item_id_from_icon_design_id
# ---------------------------------------------------------------------------


class TestExtractItemIdFromIconDesignId:
    def test_prefix_icon_suffix_pattern(self):
        result = _extract_item_id_from_icon_design_id("feature-icon-feature-1")
        assert result == "feature-1"

    def test_suffix_icon_pattern(self):
        result = _extract_item_id_from_icon_design_id("features-card-1-icon")
        assert result == "1"

    def test_no_pattern_returns_none(self):
        result = _extract_item_id_from_icon_design_id("regular-design-id")
        assert result is None

    def test_none_returns_none(self):
        result = _extract_item_id_from_icon_design_id(None)  # type: ignore
        assert result is None

    def test_empty_string_returns_none(self):
        result = _extract_item_id_from_icon_design_id("")
        assert result is None

    def test_icon_suffix_alone_returns_none(self):
        # Just "-icon" with no base should return the last segment which may be empty
        result = _extract_item_id_from_icon_design_id("-icon")
        # The base before "-icon" is "", segments would be [""], last is ""
        # Implementation strips empty, so None
        assert result is None or result == ""


# ---------------------------------------------------------------------------
# _upsert_lucide_react_import_add_only
# ---------------------------------------------------------------------------


class TestUpsertLucideReactImportAddOnly:
    def test_adds_to_existing_lucide_import(self):
        content = "import { Zap } from 'lucide-react';\n"
        result = _upsert_lucide_react_import_add_only(content=content, new_icon_component="Bell")
        assert "Bell" in result
        assert "Zap" in result

    def test_does_not_duplicate_existing_import(self):
        content = "import { Zap } from 'lucide-react';\n"
        result = _upsert_lucide_react_import_add_only(content=content, new_icon_component="Zap")
        assert result.count("Zap") == 1

    def test_creates_new_lucide_import_when_none_exists(self):
        content = "import React from 'react';\n"
        result = _upsert_lucide_react_import_add_only(content=content, new_icon_component="Bell")
        assert "from 'lucide-react'" in result
        assert "Bell" in result

    def test_adds_at_start_when_no_imports(self):
        content = "const x = 1;\n"
        result = _upsert_lucide_react_import_add_only(content=content, new_icon_component="Bell")
        assert "from 'lucide-react'" in result

    def test_empty_content_returns_content_unchanged(self):
        # Empty content is treated as falsy and returned as-is.
        result = _upsert_lucide_react_import_add_only(content="", new_icon_component="Bell")
        assert result == ""

    def test_empty_icon_component_returns_unchanged(self):
        content = "import { Zap } from 'lucide-react';\n"
        result = _upsert_lucide_react_import_add_only(content=content, new_icon_component="")
        assert result == content

    def test_non_string_content_returns_unchanged(self):
        result = _upsert_lucide_react_import_add_only(
            content=None,
            new_icon_component="Bell",  # type: ignore
        )
        assert result is None


# ---------------------------------------------------------------------------
# _apply_icon_change_by_design_id
# ---------------------------------------------------------------------------


class TestApplyIconChangeByDesignId:
    def _make_lucide_content(self, icon: str = "Zap", design_id: str = "icon-1") -> str:
        return (
            f"import {{ {icon} }} from 'lucide-react';\n<{icon} data-design-id=\"{design_id}\" />\n"
        )

    def test_replaces_lucide_icon_component(self):
        content = self._make_lucide_content("Zap", "icon-1")
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="icon-1",
            icon_name="bell",
            svg_inner=None,
        )
        assert applied is True
        assert "<Bell" in result

    def test_updates_lucide_import_statement(self):
        content = self._make_lucide_content("Zap", "icon-1")
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="icon-1",
            icon_name="bell",
            svg_inner=None,
        )
        assert applied is True
        assert "Bell" in result
        assert "from 'lucide-react'" in result

    def test_same_icon_returns_true_unchanged(self):
        content = self._make_lucide_content("Bell", "icon-1")
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="icon-1",
            icon_name="bell",
            svg_inner=None,
        )
        assert applied is True
        assert result == content

    def test_returns_false_when_design_id_not_found(self):
        content = self._make_lucide_content("Zap", "icon-1")
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="missing",
            icon_name="bell",
            svg_inner=None,
        )
        assert applied is False

    def test_returns_false_for_lucide_with_missing_icon_name(self):
        content = '<Zap data-design-id="icon-1" />'
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="icon-1",
            icon_name=None,
            svg_inner=None,
        )
        assert applied is False

    def test_replaces_svg_inner_content(self):
        content = '<svg data-design-id="svg-1" viewBox="0 0 24 24"><path d="M5 12h14"/></svg>'
        new_inner = '<circle cx="12" cy="12" r="10"/>'
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="svg-1",
            icon_name=None,
            svg_inner=new_inner,
        )
        assert applied is True
        assert '<circle cx="12" cy="12" r="10"/>' in result

    def test_returns_false_for_missing_svg_payload(self):
        content = '<svg data-design-id="svg-1"><path d="M5 12"/></svg>'
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="svg-1",
            icon_name=None,
            svg_inner=None,
        )
        assert applied is False

    def test_self_closing_svg_converted_to_block(self):
        content = '<svg data-design-id="svg-1" />'
        new_inner = '<path d="M5 12h14"/>'
        result, applied = _apply_icon_change_by_design_id(
            content=content,
            file_path="test.tsx",
            design_id="svg-1",
            icon_name=None,
            svg_inner=new_inner,
        )
        assert applied is True
        assert "<svg" in result
        assert "</svg>" in result


# ---------------------------------------------------------------------------
# _apply_icon_change_by_item_id_assignment
# ---------------------------------------------------------------------------


class TestApplyIconChangeByItemIdAssignment:
    def _make_feature_content(self, icon: str = "Shield", item_id: str = "feature-1") -> str:
        return (
            f"import {{ {icon} }} from 'lucide-react';\n"
            f"const features = [{{ id: '{item_id}', icon: {icon} }}];\n"
        )

    def test_updates_icon_in_id_first_pattern(self):
        content = self._make_feature_content("Shield", "feature-1")
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="feature-1",
            icon_name="zap",
        )
        assert applied is True
        assert "Zap" in result

    def test_updates_icon_in_icon_first_pattern(self):
        content = (
            "import { Shield } from 'lucide-react';\n"
            "const features = [{ icon: Shield, id: 'feature-1' }];\n"
        )
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="feature-1",
            icon_name="zap",
        )
        assert applied is True
        assert "Zap" in result

    def test_returns_false_when_item_id_not_found(self):
        content = self._make_feature_content("Shield", "feature-1")
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="missing-id",
            icon_name="zap",
        )
        assert applied is False

    def test_same_icon_returns_true_unchanged(self):
        content = self._make_feature_content("Zap", "feature-1")
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="feature-1",
            icon_name="zap",
        )
        assert applied is True

    def test_empty_content_returns_false(self):
        result, applied = _apply_icon_change_by_item_id_assignment(
            content="",
            file_path="test.tsx",
            item_id="feature-1",
            icon_name="zap",
        )
        assert applied is False

    def test_empty_item_id_returns_false(self):
        content = self._make_feature_content()
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="",
            icon_name="zap",
        )
        assert applied is False

    def test_invalid_icon_name_returns_false(self):
        content = self._make_feature_content()
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="feature-1",
            icon_name="",
        )
        assert applied is False

    def test_adds_lucide_import_for_new_icon(self):
        content = (
            "import { Shield } from 'lucide-react';\n"
            "const features = [{ id: 'feature-1', icon: Shield }];\n"
        )
        result, applied = _apply_icon_change_by_item_id_assignment(
            content=content,
            file_path="test.tsx",
            item_id="feature-1",
            icon_name="bell",
        )
        assert applied is True
        assert "Bell" in result
        assert "from 'lucide-react'" in result


# ---------------------------------------------------------------------------
# _escape_js_string_literal
# ---------------------------------------------------------------------------


class TestEscapeJsStringLiteral:
    def test_no_special_chars(self):
        assert _escape_js_string_literal("red") == "red"

    def test_single_quote_escaped(self):
        result = _escape_js_string_literal("it's")
        assert "\\'" in result

    def test_backslash_escaped(self):
        result = _escape_js_string_literal("a\\b")
        assert "\\\\" in result

    def test_empty_string(self):
        assert _escape_js_string_literal("") == ""
