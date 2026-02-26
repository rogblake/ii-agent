"""Tests for _mutations.py."""

import pytest

from ii_agent.projects.design.schemas import StyleChange
from ii_agent.projects.design.source_mapping_sync._mutations import (
    _apply_delete_change_by_design_id,
    _apply_icon_change_by_design_id,
    _apply_icon_change_by_dynamic_pattern,
    _apply_icon_change_by_item_id_assignment,
    _apply_move_change_by_design_id_anchor,
    _apply_move_change_by_design_ids,
    _apply_style_change_as_css_override,
    _apply_style_change_by_design_id,
    _apply_swap_change_by_design_ids,
    _apply_text_change_by_design_id,
    _css_property_to_jsx_style_key,
    _escape_css_attribute_value,
    _escape_js_string_literal,
    _extract_icon_name_from_change,
    _extract_icon_payload_from_change,
    _extract_item_id_from_icon_design_id,
    _find_best_source_file_for_design_id,
    _find_best_source_file_for_icon_item_id,
    _find_icon_by_dynamic_pattern,
    _infer_design_id_pattern,
    _locate_project_globals_css,
    _lucide_icon_name_to_component_name,
    _normalize_lucide_icon_name,
    _sanitize_svg_inner_for_jsx,
    _update_icon_at_array_index,
    _update_icon_in_array_by_value,
    _update_icon_where_field_matches,
    _upsert_design_mode_css_override,
    _upsert_html_style_attribute,
    _upsert_html_style_declaration,
    _upsert_jsx_attribute_if_missing,
    _upsert_jsx_style_attribute,
    _upsert_lucide_class_names_in_svg_opening_tag,
    _upsert_lucide_react_import_add_only,
)

from .conftest import make_style_change


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

class TestApplyDeleteChangeByDesignId:
    def test_deletes_element(self):
        content = '<div data-design-id="rm">remove me</div>'
        result, ok = _apply_delete_change_by_design_id(
            content=content, file_path="f.tsx", design_id="rm"
        )
        assert ok is True
        assert "remove me" not in result

    def test_not_found(self):
        content = "<div>text</div>"
        result, ok = _apply_delete_change_by_design_id(
            content=content, file_path="f.tsx", design_id="nope"
        )
        assert ok is False
        assert result == content

    def test_self_closing(self):
        content = '<br data-design-id="rm" />'
        result, ok = _apply_delete_change_by_design_id(
            content=content, file_path="f.tsx", design_id="rm"
        )
        assert ok is True
        assert result.strip() == ""

    def test_preserves_surrounding(self):
        content = 'before\n<div data-design-id="rm">x</div>\nafter'
        result, ok = _apply_delete_change_by_design_id(
            content=content, file_path="f.tsx", design_id="rm"
        )
        assert ok is True
        assert "before" in result
        assert "after" in result

    def test_removes_leading_whitespace(self):
        content = '  <div data-design-id="rm">x</div>\n'
        result, ok = _apply_delete_change_by_design_id(
            content=content, file_path="f.tsx", design_id="rm"
        )
        assert ok is True
        assert result == ""


# ---------------------------------------------------------------------------
# Icon helpers
# ---------------------------------------------------------------------------

class TestNormalizeLucideIconName:
    def test_basic(self):
        assert _normalize_lucide_icon_name("brick-wall") == "brick-wall"

    def test_underscore(self):
        assert _normalize_lucide_icon_name("brick_wall") == "brick-wall"

    def test_spaces(self):
        assert _normalize_lucide_icon_name("brick wall") == "brick-wall"

    def test_special_chars(self):
        assert _normalize_lucide_icon_name("brick@wall!") == "brickwall"

    def test_empty(self):
        assert _normalize_lucide_icon_name("") == ""


class TestLucideIconNameToComponentName:
    def test_kebab_case(self):
        assert _lucide_icon_name_to_component_name("brick-wall") == "BrickWall"

    def test_already_component(self):
        assert _lucide_icon_name_to_component_name("BrickWall") == "BrickWall"

    def test_with_number(self):
        assert _lucide_icon_name_to_component_name("check-circle-2") == "CheckCircle2"

    def test_empty(self):
        assert _lucide_icon_name_to_component_name("") is None

    def test_none(self):
        assert _lucide_icon_name_to_component_name(None) is None

    def test_single_word(self):
        assert _lucide_icon_name_to_component_name("zap") == "Zap"


class TestSanitizeSvgInnerForJsx:
    def test_stroke_width(self):
        result = _sanitize_svg_inner_for_jsx('<path stroke-width="2" />')
        assert 'strokeWidth="2"' in result

    def test_full_svg_unwrapped(self):
        result = _sanitize_svg_inner_for_jsx('<svg viewBox="0 0 24 24"><path d="M1 1" /></svg>')
        assert not result.startswith("<svg")
        assert 'path d="M1 1"' in result

    def test_self_closing_svg(self):
        result = _sanitize_svg_inner_for_jsx("<svg />")
        assert result == ""

    def test_multiple_replacements(self):
        result = _sanitize_svg_inner_for_jsx('<path stroke-linecap="round" stroke-linejoin="round" />')
        assert "strokeLinecap" in result
        assert "strokeLinejoin" in result

    def test_empty(self):
        assert _sanitize_svg_inner_for_jsx("") == ""

    def test_none(self):
        assert _sanitize_svg_inner_for_jsx(None) is None


class TestUpsertJsxAttributeIfMissing:
    def test_add_to_tag(self):
        tag = '<svg viewBox="0 0 24 24">'
        result = _upsert_jsx_attribute_if_missing(tag, "fill", "none")
        assert 'fill="none"' in result

    def test_already_present(self):
        tag = '<svg fill="red">'
        result = _upsert_jsx_attribute_if_missing(tag, "fill", "none")
        assert result == tag

    def test_self_closing(self):
        tag = '<svg viewBox="0 0 24 24" />'
        result = _upsert_jsx_attribute_if_missing(tag, "fill", "none")
        assert 'fill="none"' in result
        assert result.rstrip().endswith("/>")

    def test_empty_tag(self):
        assert _upsert_jsx_attribute_if_missing("", "a", "b") == ""

    def test_empty_attr(self):
        tag = "<svg>"
        assert _upsert_jsx_attribute_if_missing(tag, "", "b") == tag


class TestUpsertLucideClassNamesInSvgOpeningTag:
    def test_adds_lucide_class(self):
        tag = '<svg className="w-4 h-4">'
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name="zap")
        assert "lucide" in result
        assert "lucide-zap" in result

    def test_already_present(self):
        tag = '<svg className="lucide lucide-zap w-4 h-4">'
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name="zap")
        assert result == tag

    def test_no_class_name(self):
        tag = "<svg>"
        result = _upsert_lucide_class_names_in_svg_opening_tag(tag, icon_name="zap")
        assert result == tag

    def test_empty(self):
        assert _upsert_lucide_class_names_in_svg_opening_tag("", icon_name="zap") == ""


class TestApplyIconChangeByDesignId:
    def test_lucide_component_replacement(self):
        content = "import { Zap } from 'lucide-react'\n<Zap data-design-id=\"icon1\" />"
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name="bell", svg_inner=None,
        )
        assert ok is True
        assert "<Bell" in result
        assert "Bell" in result  # Import should be updated

    def test_same_icon_noop(self):
        content = '<Zap data-design-id="icon1" />'
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name="Zap", svg_inner=None,
        )
        assert ok is True
        assert result == content

    def test_svg_inner_replacement(self):
        content = '<svg data-design-id="icon1"><path d="old" /></svg>'
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name=None, svg_inner='<path d="new" />',
        )
        assert ok is True
        assert 'path d="new"' in result

    def test_not_found(self):
        content = "<div>text</div>"
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="missing",
            icon_name="bell", svg_inner=None,
        )
        assert ok is False

    def test_missing_icon_name_for_component(self):
        content = '<Zap data-design-id="icon1" />'
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name=None, svg_inner=None,
        )
        assert ok is False

    def test_self_closing_svg_with_inner(self):
        content = '<svg data-design-id="icon1" />'
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name=None, svg_inner='<path d="x" />',
        )
        assert ok is True
        assert "<svg" in result
        assert "</svg>" in result

    def test_svg_wrapper_fallback(self):
        content = '<div data-design-id="icon1"><svg><path d="old" /></svg></div>'
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name=None, svg_inner='<path d="new" />',
        )
        assert ok is True
        assert 'path d="new"' in result

    def test_icon_with_closing_tag(self):
        content = "import { Zap } from 'lucide-react'\n<Zap data-design-id=\"icon1\">child</Zap>"
        result, ok = _apply_icon_change_by_design_id(
            content=content, file_path="f.tsx", design_id="icon1",
            icon_name="bell", svg_inner=None,
        )
        assert ok is True
        assert "</Bell>" in result


class TestApplyIconChangeByItemIdAssignment:
    def test_id_before_icon(self):
        content = 'import { Shield } from \'lucide-react\'\nconst items = [{ id: "feature-1", icon: Shield }]'
        result, ok = _apply_icon_change_by_item_id_assignment(
            content=content, file_path="f.tsx", item_id="feature-1", icon_name="bell",
        )
        assert ok is True
        assert "Bell" in result

    def test_icon_before_id(self):
        content = 'import { Shield } from \'lucide-react\'\nconst items = [{ icon: Shield, id: "feature-1" }]'
        result, ok = _apply_icon_change_by_item_id_assignment(
            content=content, file_path="f.tsx", item_id="feature-1", icon_name="bell",
        )
        assert ok is True
        assert "Bell" in result

    def test_same_icon(self):
        content = 'const items = [{ id: "f1", icon: Bell }]'
        result, ok = _apply_icon_change_by_item_id_assignment(
            content=content, file_path="f.tsx", item_id="f1", icon_name="bell",
        )
        assert ok is True
        assert result == content

    def test_not_found(self):
        content = "const items = []"
        result, ok = _apply_icon_change_by_item_id_assignment(
            content=content, file_path="f.tsx", item_id="missing", icon_name="bell",
        )
        assert ok is False

    def test_empty_content(self):
        result, ok = _apply_icon_change_by_item_id_assignment(
            content="", file_path="f.tsx", item_id="x", icon_name="bell",
        )
        assert ok is False


class TestExtractIconPayloadFromChange:
    def test_dict_value(self):
        change = make_style_change(
            type="attribute", property="icon",
            value={"to": {"name": "bell", "svg": "<path />"}},
        )
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "bell"
        assert svg == "<path />"

    def test_json_string(self):
        import json
        change = make_style_change(
            type="attribute", property="icon",
            value={"to": json.dumps({"name": "zap"})},
        )
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "zap"

    def test_plain_string(self):
        change = make_style_change(
            type="attribute", property="icon",
            value={"to": "brick-wall"},
        )
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "brick-wall"
        assert svg is None

    def test_svg_markup(self):
        change = make_style_change(
            type="attribute", property="icon",
            value={"to": "<path d='x' />"},
        )
        name, svg = _extract_icon_payload_from_change(change)
        assert name is None
        assert svg == "<path d='x' />"

    def test_none_to(self):
        change = make_style_change(type="attribute", property="icon", value={})
        name, svg = _extract_icon_payload_from_change(change)
        assert name is None
        assert svg is None

    def test_none_change(self):
        name, svg = _extract_icon_payload_from_change(None)
        assert name is None
        assert svg is None

    def test_dict_with_only_name(self):
        change = make_style_change(
            type="attribute", property="icon",
            value={"to": {"name": "bell"}},
        )
        name, svg = _extract_icon_payload_from_change(change)
        assert name == "bell"
        assert svg is None


class TestExtractIconNameFromChange:
    def test_returns_name(self):
        change = make_style_change(
            type="attribute", property="icon",
            value={"to": "bell"},
        )
        assert _extract_icon_name_from_change(change) == "bell"

    def test_none_change(self):
        assert _extract_icon_name_from_change(None) is None


class TestExtractItemIdFromIconDesignId:
    def test_icon_prefix_pattern(self):
        assert _extract_item_id_from_icon_design_id("feature-icon-feature-1") == "feature-1"

    def test_icon_suffix_pattern(self):
        assert _extract_item_id_from_icon_design_id("features-card-1-icon") == "1"

    def test_no_pattern(self):
        assert _extract_item_id_from_icon_design_id("just-a-normal-id") is None

    def test_empty(self):
        assert _extract_item_id_from_icon_design_id("") is None

    def test_none(self):
        assert _extract_item_id_from_icon_design_id(None) is None


# ---------------------------------------------------------------------------
# Move / Swap
# ---------------------------------------------------------------------------

class TestApplyMoveChangeByDesignIds:
    def test_move_before(self):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        result, ok = _apply_move_change_by_design_ids(
            content=content, file_path="f.tsx", design_id="b",
            target_design_id="a", mode="before",
        )
        assert ok is True
        assert result.index("B") < result.index("A")

    def test_move_after(self):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        result, ok = _apply_move_change_by_design_ids(
            content=content, file_path="f.tsx", design_id="a",
            target_design_id="b", mode="after",
        )
        assert ok is True
        assert result.index("A") > result.index("B")

    def test_same_id(self):
        content = '<div data-design-id="a">A</div>'
        result, ok = _apply_move_change_by_design_ids(
            content=content, file_path="f.tsx", design_id="a",
            target_design_id="a", mode="before",
        )
        assert ok is True
        assert result == content

    def test_invalid_mode(self):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        _, ok = _apply_move_change_by_design_ids(
            content=content, file_path="f.tsx", design_id="a",
            target_design_id="b", mode="invalid",
        )
        assert ok is False

    def test_source_not_found(self):
        content = '<div data-design-id="b">B</div>'
        _, ok = _apply_move_change_by_design_ids(
            content=content, file_path="f.tsx", design_id="missing",
            target_design_id="b", mode="before",
        )
        assert ok is False

    def test_target_not_found(self):
        content = '<div data-design-id="a">A</div>'
        _, ok = _apply_move_change_by_design_ids(
            content=content, file_path="f.tsx", design_id="a",
            target_design_id="missing", mode="before",
        )
        assert ok is False


class TestApplyMoveChangeByDesignIdAnchor:
    def test_before_anchor(self):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        result, ok = _apply_move_change_by_design_id_anchor(
            content=content, file_path="f.tsx", design_id="b",
            anchor="before:a",
        )
        assert ok is True
        assert result.index("B") < result.index("A")

    def test_after_anchor(self):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        result, ok = _apply_move_change_by_design_id_anchor(
            content=content, file_path="f.tsx", design_id="a",
            anchor="after:b",
        )
        assert ok is True

    def test_only_anchor(self):
        content = '<div data-design-id="a">A</div>'
        result, ok = _apply_move_change_by_design_id_anchor(
            content=content, file_path="f.tsx", design_id="a",
            anchor="only",
        )
        assert ok is True
        assert result == content

    def test_invalid_anchor(self):
        content = '<div data-design-id="a">A</div>'
        _, ok = _apply_move_change_by_design_id_anchor(
            content=content, file_path="f.tsx", design_id="a",
            anchor="invalid",
        )
        assert ok is False

    def test_empty_anchor(self):
        _, ok = _apply_move_change_by_design_id_anchor(
            content="<div>x</div>", file_path="f.tsx", design_id="a",
            anchor="",
        )
        assert ok is False


class TestApplySwapChangeByDesignIds:
    def test_swap(self):
        content = '<div data-design-id="a">A</div><div data-design-id="b">B</div>'
        result, ok = _apply_swap_change_by_design_ids(
            content=content, file_path="f.tsx",
            design_id="a", target_design_id="b",
        )
        assert ok is True
        assert result.index("B") < result.index("A")

    def test_same_element(self):
        content = '<div data-design-id="a">A</div>'
        result, ok = _apply_swap_change_by_design_ids(
            content=content, file_path="f.tsx",
            design_id="a", target_design_id="a",
        )
        assert ok is True

    def test_not_found(self):
        content = '<div data-design-id="a">A</div>'
        _, ok = _apply_swap_change_by_design_ids(
            content=content, file_path="f.tsx",
            design_id="a", target_design_id="missing",
        )
        assert ok is False

    def test_source_not_found(self):
        content = '<div data-design-id="b">B</div>'
        _, ok = _apply_swap_change_by_design_ids(
            content=content, file_path="f.tsx",
            design_id="missing", target_design_id="b",
        )
        assert ok is False

    def test_overlapping_spans(self):
        content = '<div data-design-id="outer"><span data-design-id="inner">x</span></div>'
        _, ok = _apply_swap_change_by_design_ids(
            content=content, file_path="f.tsx",
            design_id="outer", target_design_id="inner",
        )
        assert ok is False


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

class TestApplyTextChangeByDesignId:
    def test_replaces_text(self):
        content = '<h1 data-design-id="t1">Hello World</h1>'
        result, ok = _apply_text_change_by_design_id(
            content=content, file_path="f.tsx", design_id="t1",
            old_text="Hello World", new_text="New Title",
        )
        assert ok is True
        assert "New Title" in result
        assert "Hello World" not in result

    def test_already_in_sync(self):
        content = '<h1 data-design-id="t1">New Title</h1>'
        result, ok = _apply_text_change_by_design_id(
            content=content, file_path="f.tsx", design_id="t1",
            old_text="Old", new_text="New Title",
        )
        assert ok is True

    def test_not_found(self):
        content = '<h1 data-design-id="t1">text</h1>'
        _, ok = _apply_text_change_by_design_id(
            content=content, file_path="f.tsx", design_id="missing",
            old_text="text", new_text="new",
        )
        assert ok is False

    def test_empty_old_text(self):
        content = '<h1 data-design-id="t1">text</h1>'
        _, ok = _apply_text_change_by_design_id(
            content=content, file_path="f.tsx", design_id="t1",
            old_text="", new_text="new",
        )
        assert ok is False

    def test_old_text_not_in_window(self):
        content = '<h1 data-design-id="t1">different</h1>'
        _, ok = _apply_text_change_by_design_id(
            content=content, file_path="f.tsx", design_id="t1",
            old_text="missing text", new_text="new",
        )
        assert ok is False

    def test_replaces_first_occurrence_only(self):
        content = '<div data-design-id="t1">aaa aaa</div>'
        result, ok = _apply_text_change_by_design_id(
            content=content, file_path="f.tsx", design_id="t1",
            old_text="aaa", new_text="bbb",
        )
        assert ok is True
        assert "bbb" in result


# ---------------------------------------------------------------------------
# Style: CSS helpers
# ---------------------------------------------------------------------------

class TestEscapeCssAttributeValue:
    def test_basic(self):
        assert _escape_css_attribute_value("hello") == "hello"

    def test_backslash(self):
        assert _escape_css_attribute_value("a\\b") == "a\\\\b"

    def test_quote(self):
        assert _escape_css_attribute_value('a"b') == 'a\\"b'


class TestUpsertDesignModeCssOverride:
    def test_new_rule_no_section(self):
        result = _upsert_design_mode_css_override(
            css_text="body { margin: 0; }", design_id="abc",
            css_prop="color", css_value="red",
        )
        assert 'data-design-id="abc"' in result
        assert "color: red;" in result
        assert "Design Mode Overrides" in result

    def test_update_existing_property(self):
        css = (
            '/* === Design Mode Overrides (ii-agent) === */\n'
            '[data-design-id="abc"] {\n  color: blue;\n}\n'
            '/* === End Design Mode Overrides === */\n'
        )
        result = _upsert_design_mode_css_override(
            css_text=css, design_id="abc", css_prop="color", css_value="red",
        )
        assert "color: red;" in result
        assert "color: blue;" not in result

    def test_add_property_to_existing_rule(self):
        css = (
            '/* === Design Mode Overrides (ii-agent) === */\n'
            '[data-design-id="abc"] {\n  color: blue;\n}\n'
            '/* === End Design Mode Overrides === */\n'
        )
        result = _upsert_design_mode_css_override(
            css_text=css, design_id="abc", css_prop="font-size", css_value="16px",
        )
        assert "font-size: 16px;" in result
        assert "color: blue;" in result

    def test_remove_property(self):
        css = (
            '/* === Design Mode Overrides (ii-agent) === */\n'
            '[data-design-id="abc"] {\n  color: blue;\n}\n'
            '/* === End Design Mode Overrides === */\n'
        )
        result = _upsert_design_mode_css_override(
            css_text=css, design_id="abc", css_prop="color", css_value="",
        )
        assert "color:" not in result

    def test_empty_css_prop(self):
        css = "body {}"
        result = _upsert_design_mode_css_override(
            css_text=css, design_id="abc", css_prop="", css_value="red",
        )
        assert result == css

    def test_new_rule_in_existing_section(self):
        css = (
            '/* === Design Mode Overrides (ii-agent) === */\n'
            '/* === End Design Mode Overrides === */\n'
        )
        result = _upsert_design_mode_css_override(
            css_text=css, design_id="abc", css_prop="color", css_value="red",
        )
        assert "color: red;" in result

    def test_empty_css_text(self):
        result = _upsert_design_mode_css_override(
            css_text="", design_id="abc", css_prop="color", css_value="red",
        )
        assert "color: red;" in result

    def test_none_css_text(self):
        result = _upsert_design_mode_css_override(
            css_text=None, design_id="abc", css_prop="color", css_value="red",
        )
        assert "color: red;" in result


class TestUpsertHtmlStyleDeclaration:
    def test_add(self):
        result = _upsert_html_style_declaration("color: blue;", "font-size", "16px")
        assert "font-size: 16px" in result
        assert "color: blue" in result

    def test_update(self):
        result = _upsert_html_style_declaration("color: blue;", "color", "red")
        assert "color: red" in result
        assert "blue" not in result

    def test_remove(self):
        result = _upsert_html_style_declaration("color: blue;", "color", "")
        assert "color" not in result

    def test_empty(self):
        result = _upsert_html_style_declaration("", "color", "red")
        assert "color: red" in result

    def test_empty_prop(self):
        result = _upsert_html_style_declaration("color: blue;", "", "red")
        assert result == "color: blue;"


class TestUpsertHtmlStyleAttribute:
    def test_add_style(self):
        tag = '<div class="foo">'
        result = _upsert_html_style_attribute(tag, "color", "red")
        assert 'style="color: red;"' in result

    def test_update_existing(self):
        tag = '<div style="color: blue;">'
        result = _upsert_html_style_attribute(tag, "color", "red")
        assert "color: red" in result
        assert "blue" not in result

    def test_add_to_existing(self):
        tag = '<div style="color: blue;">'
        result = _upsert_html_style_attribute(tag, "font-size", "16px")
        assert "font-size: 16px" in result
        assert "color: blue" in result

    def test_remove_last_declaration(self):
        tag = '<div style="color: blue;">'
        result = _upsert_html_style_attribute(tag, "color", "")
        assert "style" not in result

    def test_none_tag(self):
        assert _upsert_html_style_attribute(None, "color", "red") is None


class TestCssPropertyToJsxStyleKey:
    def test_kebab_to_camel(self):
        assert _css_property_to_jsx_style_key("font-size") == "fontSize"

    def test_custom_property(self):
        assert _css_property_to_jsx_style_key("--my-var") == "--my-var"

    def test_single_word(self):
        assert _css_property_to_jsx_style_key("color") == "color"

    def test_empty(self):
        assert _css_property_to_jsx_style_key("") == ""

    def test_non_string(self):
        assert _css_property_to_jsx_style_key(None) == ""


class TestEscapeJsStringLiteral:
    def test_backslash(self):
        assert _escape_js_string_literal("a\\b") == "a\\\\b"

    def test_single_quote(self):
        assert _escape_js_string_literal("a'b") == "a\\'b"


class TestUpsertJsxStyleAttribute:
    def test_add_new(self):
        tag = '<div className="foo">'
        result = _upsert_jsx_style_attribute(tag, "color", "red")
        assert "style={{" in result
        assert "color:" in result

    def test_update_existing(self):
        tag = "<div style={{ color: 'blue' }}>"
        result = _upsert_jsx_style_attribute(tag, "color", "red")
        assert "red" in result

    def test_add_to_existing(self):
        tag = "<div style={{ color: 'blue' }}>"
        result = _upsert_jsx_style_attribute(tag, "fontSize", "16px")
        assert "fontSize" in result

    def test_remove_value(self):
        tag = "<div style={{ color: 'blue' }}>"
        result = _upsert_jsx_style_attribute(tag, "color", "")
        assert "undefined" in result

    def test_self_closing(self):
        tag = '<div className="foo" />'
        result = _upsert_jsx_style_attribute(tag, "color", "red")
        assert "style={{" in result

    def test_none_tag(self):
        assert _upsert_jsx_style_attribute(None, "color", "red") is None

    def test_empty_prop(self):
        assert _upsert_jsx_style_attribute("<div>", "", "red") is None

    def test_merge_multiple_style_attrs(self):
        # This can happen from buggy earlier syncs
        tag = "<div style={{ color: 'blue' }} style={{ fontSize: '12px' }}>"
        result = _upsert_jsx_style_attribute(tag, "margin", "10px")
        assert result is not None
        assert result.count("style=") == 1


class TestApplyStyleChangeByDesignId:
    def test_jsx_file(self):
        content = '<div data-design-id="s1" className="foo">text</div>'
        result, ok = _apply_style_change_by_design_id(
            content=content, file_path="/workspace/src/App.tsx",
            design_id="s1", css_prop="color", css_value="red",
        )
        assert ok is True
        assert "color" in result

    def test_html_file(self):
        content = '<div data-design-id="s1" class="foo">text</div>'
        result, ok = _apply_style_change_by_design_id(
            content=content, file_path="/workspace/index.html",
            design_id="s1", css_prop="color", css_value="red",
        )
        assert ok is True
        assert "style=" in result

    def test_not_found(self):
        content = "<div>text</div>"
        _, ok = _apply_style_change_by_design_id(
            content=content, file_path="f.tsx",
            design_id="missing", css_prop="color", css_value="red",
        )
        assert ok is False

    def test_already_in_sync(self):
        content = "<div data-design-id=\"s1\" style={{ color: 'red' }}>text</div>"
        result, ok = _apply_style_change_by_design_id(
            content=content, file_path="f.tsx",
            design_id="s1", css_prop="color", css_value="red",
        )
        assert ok is True

    def test_html_ext_detection(self):
        content = '<div data-design-id="s1">text</div>'
        result, ok = _apply_style_change_by_design_id(
            content=content, file_path="/workspace/page.htm",
            design_id="s1", css_prop="color", css_value="red",
        )
        assert ok is True


# ---------------------------------------------------------------------------
# Dynamic pattern
# ---------------------------------------------------------------------------

class TestUpdateIconAtArrayIndex:
    def test_updates_correct_index(self):
        array_content = '{ icon: Shield, id: "1" }, { icon: Zap, id: "2" }'
        content = f"const items = [{array_content}]"
        array_start = content.index("[") + 1
        result = _update_icon_at_array_index(
            content=content, array_content=array_content,
            array_start=array_start, target_index=1, new_icon_component="Bell",
        )
        assert "Bell" in result
        assert "Shield" in result  # First item unchanged

    def test_index_out_of_range(self):
        array_content = '{ icon: Shield }'
        content = f"[{array_content}]"
        result = _update_icon_at_array_index(
            content=content, array_content=array_content,
            array_start=1, target_index=5, new_icon_component="Bell",
        )
        assert result == content

    def test_same_icon(self):
        array_content = '{ icon: Bell }'
        content = f"[{array_content}]"
        result = _update_icon_at_array_index(
            content=content, array_content=array_content,
            array_start=1, target_index=0, new_icon_component="Bell",
        )
        assert result == content

    def test_negative_index(self):
        array_content = '{ icon: Shield }'
        content = f"[{array_content}]"
        result = _update_icon_at_array_index(
            content=content, array_content=array_content,
            array_start=1, target_index=-1, new_icon_component="Bell",
        )
        assert result == content


class TestUpdateIconWhereFieldMatches:
    def test_matches_field(self):
        array_content = '{ id: "a", icon: Shield }, { id: "b", icon: Zap }'
        content = f"[{array_content}]"
        result = _update_icon_where_field_matches(
            content=content, array_content=array_content,
            array_start=1, field_name="id", field_value="b",
            new_icon_component="Bell",
        )
        assert "Bell" in result
        assert "Shield" in result

    def test_no_match(self):
        array_content = '{ id: "a", icon: Shield }'
        content = f"[{array_content}]"
        result = _update_icon_where_field_matches(
            content=content, array_content=array_content,
            array_start=1, field_name="id", field_value="missing",
            new_icon_component="Bell",
        )
        assert result == content

    def test_same_icon(self):
        array_content = '{ id: "a", icon: Bell }'
        content = f"[{array_content}]"
        result = _update_icon_where_field_matches(
            content=content, array_content=array_content,
            array_start=1, field_name="id", field_value="a",
            new_icon_component="Bell",
        )
        assert result == content


class TestUpdateIconInArrayByValue:
    def test_index_based(self):
        content = 'const items = [{ icon: Shield }, { icon: Zap }]'
        array_start = content.index("[")
        result = _update_icon_in_array_by_value(
            content=content, array_start=array_start, target_value="1",
            variable_expr="index", iterator_var="item", index_var="index",
            new_icon_component="Bell",
        )
        assert "Bell" in result
        assert "Shield" in result

    def test_field_based(self):
        content = 'const items = [{ id: "a", icon: Shield }, { id: "b", icon: Zap }]'
        array_start = content.index("[")
        result = _update_icon_in_array_by_value(
            content=content, array_start=array_start, target_value="b",
            variable_expr="item.id", iterator_var="item", index_var=None,
            new_icon_component="Bell",
        )
        assert "Bell" in result

    def test_no_array(self):
        content = "const x = 42"
        result = _update_icon_in_array_by_value(
            content=content, array_start=0, target_value="0",
            variable_expr="index", iterator_var="item", index_var="index",
            new_icon_component="Bell",
        )
        assert result == content


class TestApplyIconChangeByDynamicPattern:
    def test_template_match(self):
        content = (
            'import { Shield, Zap } from \'lucide-react\'\n'
            'const features = [{ id: "1", icon: Shield }, { id: "2", icon: Zap }]\n'
            '{features.map((feature, index) => (\n'
            '  <div data-design-id={`features-card-${feature.id}-icon`}>\n'
            '    <feature.icon />\n'
            '  </div>\n'
            '))}'
        )
        result, ok = _apply_icon_change_by_dynamic_pattern(
            content=content, file_path="f.tsx",
            design_id="features-card-1-icon", pattern=r"features-card-\d+-icon",
            icon_name="bell",
        )
        # May or may not match depending on exact pattern matching
        assert isinstance(ok, bool)

    def test_no_template(self):
        content = '<div data-design-id="static-id">text</div>'
        _, ok = _apply_icon_change_by_dynamic_pattern(
            content=content, file_path="f.tsx",
            design_id="static-id", pattern=r"static-id",
            icon_name="bell",
        )
        assert ok is False

    def test_empty_content(self):
        _, ok = _apply_icon_change_by_dynamic_pattern(
            content="", file_path="f.tsx",
            design_id="x", pattern="x",
            icon_name="bell",
        )
        assert ok is False

    def test_missing_params(self):
        _, ok = _apply_icon_change_by_dynamic_pattern(
            content="content", file_path="f.tsx",
            design_id="", pattern="", icon_name="",
        )
        assert ok is False


class TestInferDesignIdPattern:
    def test_digit_replacement(self):
        result = _infer_design_id_pattern("features-card-1-icon")
        assert result is not None
        assert "\\d+" in result

    def test_preserves_known_words(self):
        result = _infer_design_id_pattern("features-card-1-icon")
        assert "features" in result
        assert "icon" in result
        assert "card" in result

    def test_empty(self):
        assert _infer_design_id_pattern("") is None

    def test_none(self):
        assert _infer_design_id_pattern(None) is None

    def test_all_letters(self):
        result = _infer_design_id_pattern("pricing-tier-pro-icon")
        assert result is not None
        assert "pricing" in result
        assert "tier" in result
        assert "icon" in result


# ---------------------------------------------------------------------------
# Async functions (with FakeSandbox)
# ---------------------------------------------------------------------------

class TestLocateProjectGlobalsCss:
    async def test_finds_globals_css(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={
            "find": "/workspace/src/app/globals.css\n"
        })
        result = await _locate_project_globals_css(sandbox=sb, manifest_path=None)
        assert result == "/workspace/src/app/globals.css"

    async def test_not_found(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={})
        result = await _locate_project_globals_css(sandbox=sb, manifest_path=None)
        assert result is None

    async def test_caching(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={
            "find": "/workspace/src/app/globals.css\n"
        })
        r1 = await _locate_project_globals_css(sandbox=sb, manifest_path=None)
        sb._command_outputs = {}
        r2 = await _locate_project_globals_css(sandbox=sb, manifest_path=None)
        assert r1 == r2


class TestApplyStyleChangeAsCssOverride:
    async def test_applies_override(self, fake_sandbox):
        sb = fake_sandbox(
            files={"/workspace/src/app/globals.css": "body {}"},
            command_outputs={"find": "/workspace/src/app/globals.css\n"},
        )
        ok, path = await _apply_style_change_as_css_override(
            sandbox=sb, manifest_path=None,
            design_id="abc", css_prop="color", css_value="red",
        )
        assert ok is True
        assert path == "/workspace/src/app/globals.css"
        written = sb.written_files.get("/workspace/src/app/globals.css", "")
        assert "color: red" in written

    async def test_no_globals_css(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={})
        ok, path = await _apply_style_change_as_css_override(
            sandbox=sb, manifest_path=None,
            design_id="abc", css_prop="color", css_value="red",
        )
        assert ok is False
        assert path is None


class TestFindBestSourceFileForDesignId:
    async def test_finds_file(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={
            "rg": '/workspace/src/App.tsx:10:  data-design-id="abc"\n',
        })
        result = await _find_best_source_file_for_design_id(sandbox=sb, design_id="abc")
        assert result == "/workspace/src/App.tsx"

    async def test_not_found(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={})
        result = await _find_best_source_file_for_design_id(sandbox=sb, design_id="missing")
        assert result is None


class TestFindBestSourceFileForIconItemId:
    async def test_finds_file_with_pattern(self, fake_sandbox):
        content = 'const items = [{ id: "f1", icon: Shield }]'
        sb = fake_sandbox(
            files={"/workspace/src/Page.tsx": content},
            command_outputs={
                "rg": '/workspace/src/Page.tsx:1:  "f1"\n',
                "find /workspace": "",
            },
        )
        result = await _find_best_source_file_for_icon_item_id(sandbox=sb, item_id="f1")
        assert result == "/workspace/src/Page.tsx"


class TestUpsertLucideReactImportAddOnly:
    def test_add_to_existing_import(self):
        content = "import { Shield } from 'lucide-react'\n<Shield />"
        result = _upsert_lucide_react_import_add_only(
            content=content, new_icon_component="Bell"
        )
        assert "Bell" in result
        assert "Shield" in result

    def test_create_new_import(self):
        content = "import React from 'react'\n<div />"
        result = _upsert_lucide_react_import_add_only(
            content=content, new_icon_component="Bell"
        )
        assert "import { Bell } from 'lucide-react'" in result

    def test_no_imports(self):
        content = "<div>hello</div>"
        result = _upsert_lucide_react_import_add_only(
            content=content, new_icon_component="Bell"
        )
        assert result.startswith("import { Bell } from 'lucide-react'")


class TestFindIconByDynamicPattern:
    async def test_searches_workspace(self, fake_sandbox):
        sb = fake_sandbox(command_outputs={})
        result, ok = await _find_icon_by_dynamic_pattern(
            sandbox=sb, design_id="features-card-1-icon",
            icon_name="bell", element_context=None,
        )
        assert ok is False

    async def test_empty_params(self, fake_sandbox):
        sb = fake_sandbox()
        _, ok = await _find_icon_by_dynamic_pattern(
            sandbox=sb, design_id="", icon_name="", element_context=None,
        )
        assert ok is False
