from __future__ import annotations

import pytest

from ii_agent.projects.design.utils.html_patch import (
    _find_opening_tag_bounds_by_xpath,
    _strip_slide_deck_xpath_prefix,
    apply_slide_delete_change_with_status,
    apply_slide_icon_change_with_status,
    apply_slide_move_change_with_status,
    apply_slide_style_change_with_status,
    apply_slide_swap_change_with_status,
    apply_slide_text_change_with_status,
)


def test_apply_slide_style_change_updates_existing_property():
    html = '<div data-design-id="hero" style="color: blue; padding: 4px;">Hello</div>'
    updated, ok = apply_slide_style_change_with_status(
        html,
        "hero",
        "color",
        "red",
    )

    assert ok is True
    assert "color: red;" in updated
    assert "padding: 4px;" in updated


def test_apply_slide_style_change_with_xpath_fallback():
    html = "<div><span>Text</span></div>"
    updated, ok = apply_slide_style_change_with_status(
        html,
        "missing",
        "fontSize",
        "20px",
        xpath="/div/span",
    )

    assert ok is True
    assert 'style="font-size: 20px;"' in updated


def test_apply_slide_style_change_invalid_xpath_returns_false():
    html = "<div><span>Text</span></div>"
    updated, ok = apply_slide_style_change_with_status(
        html,
        "missing",
        "fontSize",
        "20px",
        xpath="/div/section[2]",
    )

    assert ok is False
    assert updated == html


def test_apply_slide_text_change_replaces_text_nodes():
    html = '<p data-design-id="title">Old <strong>bold</strong> value</p>'
    updated, ok = apply_slide_text_change_with_status(html, "title", "New title")

    assert ok is True
    assert "New title" in updated
    assert "<strong>bold</strong>" in updated
    assert "Old" not in updated


def test_apply_slide_text_change_rejects_self_closing_tag():
    html = '<img data-design-id="img1" src="x.png" />'
    updated, ok = apply_slide_text_change_with_status(html, "img1", "ignored")

    assert ok is False
    assert updated == html


def test_apply_slide_icon_change_material_icon_text_branch():
    html = '<i data-design-id="icon1" class="material-icons">face</i>'
    updated, ok = apply_slide_icon_change_with_status(
        html,
        "icon1",
        '{"name":"home"}',
    )

    assert ok is True
    assert ">home</i>" in updated


def test_apply_slide_icon_change_svg_wrapper_insertion():
    html = '<span data-design-id="icon-slot">Label</span>'
    updated, ok = apply_slide_icon_change_with_status(
        html,
        "icon-slot",
        "<path d='M1 1' />",
    )

    assert ok is True
    assert "<svg" in updated
    assert "<path d='M1 1' />" in updated


def test_apply_slide_icon_change_invalid_target_and_xpath():
    html = "<div><span>hello</span></div>"
    updated, ok = apply_slide_icon_change_with_status(
        html,
        "missing",
        '{"name":"zap"}',
        xpath="/div/section",
    )

    assert ok is False
    assert updated == html


def test_apply_slide_delete_change_removes_block_with_newline():
    html = 'before\n  <div data-design-id="gone">x</div>\nafter'
    updated, ok = apply_slide_delete_change_with_status(html, design_id="gone")

    assert ok is True
    assert "gone" not in updated
    assert "before" in updated and "after" in updated


def test_apply_slide_swap_change_success_and_overlap_guard():
    html = '<div data-design-id="a">A</div>\n<div data-design-id="b">B</div>'
    updated, ok = apply_slide_swap_change_with_status(
        html,
        design_id="a",
        target_design_id="b",
    )
    assert ok is True
    assert updated.index("B") < updated.index("A")

    nested = '<div data-design-id="a"><span data-design-id="b">B</span></div>'
    updated_nested, ok_nested = apply_slide_swap_change_with_status(
        nested,
        design_id="a",
        target_design_id="b",
    )
    assert ok_nested is False
    assert updated_nested == nested


def test_apply_slide_move_change_paths():
    html = (
        '<div data-design-id="a">A</div>\n'
        '<div data-design-id="b">B</div>\n'
        '<div data-design-id="c">C</div>'
    )
    moved_before, ok_before = apply_slide_move_change_with_status(
        html,
        design_id="c",
        anchor="before:a",
    )
    assert ok_before is True
    assert moved_before.index("C") < moved_before.index("A")

    moved_after, ok_after = apply_slide_move_change_with_status(
        html,
        design_id="a",
        anchor="after:c",
    )
    assert ok_after is True
    assert moved_after.index("A") > moved_after.index("C")

    unchanged, ok_only = apply_slide_move_change_with_status(
        html,
        design_id="a",
        anchor="only",
    )
    assert ok_only is True
    assert unchanged == html

    invalid, ok_invalid = apply_slide_move_change_with_status(
        html,
        design_id="a",
        anchor="before:",
    )
    assert ok_invalid is False
    assert invalid == html


def test_strip_slide_deck_xpath_prefix_and_opening_tag_bounds():
    full_xpath = "/html/body/div/div[2]/div/section/div[3]"
    stripped = _strip_slide_deck_xpath_prefix(full_xpath, slide_number=2)
    assert stripped == "/section/div[3]"

    bad = _strip_slide_deck_xpath_prefix("/html/body/div", slide_number=2)
    assert bad is None

    html = "<section><div></div><div></div><div id='t'></div></section>"
    bounds = _find_opening_tag_bounds_by_xpath(html, "/section/div[3]")
    assert bounds is not None
    start, end = bounds
    assert html[start : end + 1].startswith("<div")
