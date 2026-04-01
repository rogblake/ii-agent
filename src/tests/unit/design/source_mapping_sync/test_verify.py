"""Tests for _verify.py."""

import pytest

from ii_agent.projects.design.source_mapping_sync._verify import (
    _extract_class_attr_from_outer_html,
    _extract_literal_class_attr_from_tag,
    _verify_design_mode_target_matches_context,
)

from .conftest import make_element_context, make_style_change


# ---------------------------------------------------------------------------
# _extract_class_attr_from_outer_html
# ---------------------------------------------------------------------------


class TestExtractClassAttrFromOuterHtml:
    def test_extracts_class(self):
        html = '<div class="foo bar">text</div>'
        assert _extract_class_attr_from_outer_html(html) == "foo bar"

    def test_single_quoted(self):
        html = "<div class='foo bar'>text</div>"
        assert _extract_class_attr_from_outer_html(html) == "foo bar"

    def test_no_class(self):
        assert _extract_class_attr_from_outer_html("<div>text</div>") is None

    def test_empty_class(self):
        assert _extract_class_attr_from_outer_html('<div class="">text</div>') is None

    def test_non_string(self):
        assert _extract_class_attr_from_outer_html(42) is None


# ---------------------------------------------------------------------------
# _extract_literal_class_attr_from_tag
# ---------------------------------------------------------------------------


class TestExtractLiteralClassAttrFromTag:
    def test_class_name(self):
        tag = '<div className="foo bar">'
        assert _extract_literal_class_attr_from_tag(tag) == "foo bar"

    def test_class(self):
        tag = '<div class="foo bar">'
        assert _extract_literal_class_attr_from_tag(tag) == "foo bar"

    def test_prefers_class_name(self):
        tag = '<div className="jsx" class="html">'
        assert _extract_literal_class_attr_from_tag(tag) == "jsx"

    def test_empty_class(self):
        assert _extract_literal_class_attr_from_tag('<div className="">') is None

    def test_no_class(self):
        assert _extract_literal_class_attr_from_tag("<div>") is None

    def test_none(self):
        assert _extract_literal_class_attr_from_tag(None) is None


# ---------------------------------------------------------------------------
# _verify_design_mode_target_matches_context
# ---------------------------------------------------------------------------


class TestVerifyDesignModeTargetMatchesContext:
    def test_no_context_ok(self):
        change = make_style_change(element_context=None)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id">text</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True
        assert reason == "no_context"

    def test_tag_not_found_ok(self):
        ctx = make_element_context(tag_name="div")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content="<div>no design id</div>",
            file_path="/workspace/src/App.tsx",
            design_id="missing",
        )
        assert ok is True
        assert reason == "tag_not_found"

    def test_matching_tag(self):
        ctx = make_element_context(tag_name="div", text_content="hello")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id">hello</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True

    def test_tag_mismatch(self):
        ctx = make_element_context(tag_name="span")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id">text</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is False
        assert "tag_name_mismatch" in reason

    def test_react_component_bypass(self):
        # React components render as lowercase DOM tags at runtime,
        # so a mismatch between div (runtime) and CustomCard (source) is ok
        # because CustomCard is NOT an HTML tag name.
        ctx = make_element_context(tag_name="div")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<CustomCard data-design-id="test-id">text</CustomCard>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True

    def test_anchor_present(self):
        ctx = make_element_context(tag_name="div", text_content="Hello World")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id">Hello World</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True

    def test_anchor_missing(self):
        ctx = make_element_context(tag_name="div", text_content="Expected Text")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id">Completely different</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is False
        assert "anchor_text_mismatch" in reason

    def test_class_overlap_pass(self):
        ctx = make_element_context(tag_name="div", class_name="foo bar")
        change = make_style_change(element_context=ctx)
        ok, _ = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id" className="foo bar baz">text</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True

    def test_class_overlap_fail(self):
        ctx = make_element_context(tag_name="div", class_name="foo bar baz")
        change = make_style_change(element_context=ctx)
        ok, reason = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id" className="completely different">text</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is False
        assert "class_token_mismatch" in reason

    def test_outer_html_fallback(self):
        ctx = make_element_context(
            tag_name="div",
            class_name=None,
            outer_html='<div class="abc">text</div>',
        )
        change = make_style_change(element_context=ctx)
        ok, _ = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id" className="abc">text</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True

    def test_anchors_skip_class_check(self):
        # When anchors are found, class mismatch should not be fatal
        ctx = make_element_context(
            tag_name="div",
            class_name="totally-different-class",
            text_content="anchor text here",
        )
        change = make_style_change(element_context=ctx)
        ok, _ = _verify_design_mode_target_matches_context(
            change=change,
            content='<div data-design-id="test-id" className="other-class">anchor text here</div>',
            file_path="/workspace/src/App.tsx",
            design_id="test-id",
        )
        assert ok is True
