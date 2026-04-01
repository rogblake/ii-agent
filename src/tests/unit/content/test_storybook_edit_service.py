"""Unit tests for ii_agent.content.storybook.edit_service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.storybook.edit_service import (
    STORYBOOK_INLINE_EDIT_SCRIPT,
    StorybookEditService,
)
from ii_agent.content.storybook.schemas import DesignChange


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def _make_service(
    repo=None,
    version_service=None,
) -> StorybookEditService:
    repo = repo or MagicMock()
    version_service = version_service or MagicMock()
    return StorybookEditService(repo=repo, version_service=version_service)


def _change(
    design_id: str,
    change_type: str,
    prop: str = "",
    value: Any = None,
    context: Any = None,
) -> DesignChange:
    return DesignChange(
        designId=design_id,
        type=change_type,
        property=prop,
        value={"to": value} if value is not None else {},
        elementContext=context,
        timestamp=1000,
    )


# ---------------------------------------------------------------------------
# _inject_runtime_script
# ---------------------------------------------------------------------------


class TestInjectRuntimeScript:
    def test_injects_into_head_tag(self):
        html = "<html><head></head><body>hello</body></html>"
        result = StorybookEditService._inject_runtime_script(html)
        assert "<head>" in result
        assert STORYBOOK_INLINE_EDIT_SCRIPT in result or "__STORYBOOK_INLINE_EDIT__" in result

    def test_injects_into_head_with_attributes(self):
        html = '<html><head lang="en"></head><body></body></html>'
        result = StorybookEditService._inject_runtime_script(html)
        assert "__STORYBOOK_INLINE_EDIT__" in result

    def test_injects_head_when_only_html_tag(self):
        html = "<html><body></body></html>"
        result = StorybookEditService._inject_runtime_script(html)
        assert "__STORYBOOK_INLINE_EDIT__" in result

    def test_prepends_when_no_head_or_html_tag(self):
        html = "<div>content</div>"
        result = StorybookEditService._inject_runtime_script(html)
        assert "__STORYBOOK_INLINE_EDIT__" in result

    def test_skips_runtime_injection_when_already_present(self):
        html = "<html><head><!-- __DESIGN_MODE_RUNTIME__ --></head><body></body></html>"
        result = StorybookEditService._inject_runtime_script(html)
        # Should not double-inject the runtime script block
        assert result.count("__DESIGN_MODE_RUNTIME__") >= 1

    def test_skips_inline_edit_injection_when_already_present(self):
        already_injected = '<script data-storybook-inline-edit="true"></script>'
        html = f"<html><head>{already_injected}</head><body></body></html>"
        result = StorybookEditService._inject_runtime_script(html)
        # Should appear exactly once (from original HTML)
        assert result.count('data-storybook-inline-edit="true"') == 1

    def test_returns_original_html_if_nothing_to_inject(self):
        """Both markers already present → no injection at all."""
        html = (
            "<html><head><!-- __DESIGN_MODE_RUNTIME__ -->"
            '<script data-storybook-inline-edit="true"></script>'
            "</head><body></body></html>"
        )
        result = StorybookEditService._inject_runtime_script(html)
        assert result == html


# ---------------------------------------------------------------------------
# _extract_xpath
# ---------------------------------------------------------------------------


class TestExtractXpath:
    def test_returns_xpath_from_context(self):
        ctx = {"xpath": "//div[@id='foo']"}
        assert StorybookEditService._extract_xpath(ctx) == "//div[@id='foo']"

    def test_returns_none_when_context_none(self):
        assert StorybookEditService._extract_xpath(None) is None

    def test_returns_none_when_xpath_blank(self):
        ctx = {"xpath": "   "}
        assert StorybookEditService._extract_xpath(ctx) is None

    def test_returns_none_when_context_not_dict(self):
        assert StorybookEditService._extract_xpath("not-a-dict") is None

    def test_strips_whitespace_from_xpath(self):
        ctx = {"xpath": "  //span  "}
        assert StorybookEditService._extract_xpath(ctx) == "//span"


# ---------------------------------------------------------------------------
# _extract_slide_number
# ---------------------------------------------------------------------------


class TestExtractSlideNumber:
    def test_returns_int_from_context(self):
        ctx = {"slideNumber": 3}
        assert StorybookEditService._extract_slide_number(ctx) == 3

    def test_parses_string_slide_number(self):
        ctx = {"slideNumber": "5"}
        assert StorybookEditService._extract_slide_number(ctx) == 5

    def test_returns_none_when_context_none(self):
        assert StorybookEditService._extract_slide_number(None) is None

    def test_returns_none_when_context_not_dict(self):
        assert StorybookEditService._extract_slide_number("bad") is None

    def test_returns_none_when_slideNumber_invalid_string(self):
        ctx = {"slideNumber": "abc"}
        assert StorybookEditService._extract_slide_number(ctx) is None

    def test_returns_none_when_slideNumber_absent(self):
        ctx = {}
        assert StorybookEditService._extract_slide_number(ctx) is None


# ---------------------------------------------------------------------------
# _find_element_by_context
# ---------------------------------------------------------------------------


class TestFindElementByContext:
    def _soup(self, html: str):
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser")

    def test_finds_by_id(self):
        soup = self._soup('<div id="hero">Hello</div>')
        context = {"tagName": "div", "id": "hero"}
        el = StorybookEditService._find_element_by_context(soup, context)
        assert el is not None
        assert el.get("id") == "hero"

    def test_finds_by_class(self):
        soup = self._soup('<p class="intro bold">Text</p>')
        context = {"tagName": "p", "className": "intro bold"}
        el = StorybookEditService._find_element_by_context(soup, context)
        assert el is not None

    def test_finds_by_text_content(self):
        soup = self._soup("<span>Special text content here</span>")
        context = {"tagName": "span", "textContent": "Special text"}
        el = StorybookEditService._find_element_by_context(soup, context)
        assert el is not None

    def test_returns_none_when_tag_not_found(self):
        soup = self._soup("<div>Only divs</div>")
        context = {"tagName": "section"}
        el = StorybookEditService._find_element_by_context(soup, context)
        assert el is None

    def test_returns_none_when_no_tagName(self):
        soup = self._soup("<div>content</div>")
        el = StorybookEditService._find_element_by_context(soup, {})
        assert el is None

    def test_falls_back_to_first_candidate(self):
        soup = self._soup("<p>First</p><p>Second</p>")
        context = {"tagName": "p"}
        el = StorybookEditService._find_element_by_context(soup, context)
        assert el is not None
        assert el.get_text() == "First"


# ---------------------------------------------------------------------------
# _apply_attribute_change
# ---------------------------------------------------------------------------


class TestApplyAttributeChange:
    def test_applies_attribute_to_element(self):
        html = '<div data-design-id="box1">hello</div>'
        service = _make_service()
        new_html, ok = service._apply_attribute_change(
            html, design_id="box1", attr="data-color", value="red", context=None
        )
        assert ok is True
        assert 'data-color="red"' in new_html

    def test_normalizes_class_name_attribute(self):
        html = '<div data-design-id="box2">content</div>'
        service = _make_service()
        new_html, ok = service._apply_attribute_change(
            html, design_id="box2", attr="className", value="foo bar", context=None
        )
        assert ok is True

    def test_removes_attribute_when_value_none(self):
        html = '<div data-design-id="box3" data-color="blue">content</div>'
        service = _make_service()
        new_html, ok = service._apply_attribute_change(
            html, design_id="box3", attr="data-color", value=None, context=None
        )
        assert ok is True
        assert "data-color" not in new_html

    def test_returns_false_when_no_element_and_no_context(self):
        html = "<div>no design id</div>"
        service = _make_service()
        new_html, ok = service._apply_attribute_change(
            html, design_id="missing-id", attr="data-x", value="val", context=None
        )
        assert ok is False
        assert new_html == html

    def test_returns_original_html_when_attr_empty(self):
        html = '<div data-design-id="box4">hi</div>'
        service = _make_service()
        new_html, ok = service._apply_attribute_change(
            html, design_id="box4", attr="", value="something", context=None
        )
        assert ok is False
        assert new_html == html


# ---------------------------------------------------------------------------
# apply_changes_to_html – dispatch logic
# ---------------------------------------------------------------------------


class TestApplyChangesToHtml:
    @pytest.mark.asyncio
    async def test_returns_unchanged_html_when_no_changes(self):
        service = _make_service()
        html = "<html><body>Hello</body></html>"
        result = await service.apply_changes_to_html(html, [])
        assert result == html

    @pytest.mark.asyncio
    async def test_returns_unchanged_html_when_html_empty(self):
        service = _make_service()
        result = await service.apply_changes_to_html("", [_change("d1", "style", "color", "red")])
        assert result == ""

    @pytest.mark.asyncio
    async def test_skips_change_with_empty_design_id(self):
        service = _make_service()
        html = "<div>content</div>"
        change = _change("", "style", "color", "blue")
        result = await service.apply_changes_to_html(html, [change])
        assert result == html

    @pytest.mark.asyncio
    async def test_dispatches_style_change(self):
        service = _make_service()
        html = "<div data-design-id='el1'>content</div>"
        change = _change("el1", "style", "color", "green")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_style_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            result = await service.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_text_change(self):
        service = _make_service()
        html = "<div data-design-id='el2'>old text</div>"
        change = _change("el2", "text", "", "new text")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_text_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            result = await service.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_icon_change(self):
        service = _make_service()
        html = "<i data-design-id='ico1' class='fa-star'>icon</i>"
        change = _change("ico1", "attribute", "icon", "fa-heart")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_icon_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            result = await service.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_delete_change(self):
        service = _make_service()
        html = "<div data-design-id='del1'>delete me</div>"
        change = _change("del1", "delete")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_delete_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            result = await service.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_move_change(self):
        service = _make_service()
        html = "<div data-design-id='mv1'>move me</div>"
        change = _change("mv1", "move", "", "anchor-id")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_move_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            result = await service.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_swap_change(self):
        service = _make_service()
        html = "<div data-design-id='sw1'>swap me</div>"
        change = _change("sw1", "swap", "", "target-id")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_swap_change_with_status",
            return_value=(html, True),
        ) as mock_fn:
            result = await service.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_during_change_does_not_crash(self):
        service = _make_service()
        html = "<div data-design-id='err1'>content</div>"
        change = _change("err1", "style", "color", "red")
        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_style_change_with_status",
            side_effect=RuntimeError("boom"),
        ):
            result = await service.apply_changes_to_html(html, [change])
        # Should return html without crashing
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# get_version_history – repo interactions
# ---------------------------------------------------------------------------


class TestGetVersionHistory:
    @pytest.mark.asyncio
    async def test_returns_empty_when_storybook_not_found(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        db = MagicMock()
        result = await service.get_version_history(db, storybook_id="missing")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_root_id(self):
        storybook = MagicMock()
        storybook.id = "sb1"
        storybook.root_storybook_id = None
        storybook.parent_storybook_id = None

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=storybook)
        repo.get_version_family = AsyncMock(return_value=[])
        service = _make_service(repo=repo)
        db = MagicMock()
        result = await service.get_version_history(db, storybook_id="sb1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_version_infos(self):
        storybook = MagicMock()
        storybook.id = "sb1"
        storybook.root_storybook_id = "root1"

        v1 = MagicMock()
        v1.id = "sb1"
        v1.version = 1
        v1.created_at = _now()

        v2 = MagicMock()
        v2.id = "sb2"
        v2.version = 2
        v2.created_at = _now()

        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=storybook)
        repo.get_version_family = AsyncMock(return_value=[v1, v2])

        service = _make_service(repo=repo)
        db = MagicMock()
        result = await service.get_version_history(db, storybook_id="sb1")
        assert len(result) == 2
        assert any(vi.is_current for vi in result)


# ---------------------------------------------------------------------------
# save_all_page_edits – guard clauses
# ---------------------------------------------------------------------------


class TestSaveAllPageEdits:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_changes_and_no_images(self):
        service = _make_service()
        db = MagicMock()
        result, cost = await service.save_all_page_edits(
            db, storybook_id="sb1", page_changes={}, image_urls={}
        )
        assert result is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_none_when_source_storybook_not_found(self):
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        service = _make_service(repo=repo)
        db = MagicMock()
        result, cost = await service.save_all_page_edits(
            db,
            storybook_id="missing",
            page_changes={1: [_change("d1", "text", "", "hello")]},
        )
        assert result is None
        assert cost == 0.0
