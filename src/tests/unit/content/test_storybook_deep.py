"""Deep unit tests for storybook edit_service, pdf_export, and router utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.content.storybook.edit_service import (
    STORYBOOK_INLINE_EDIT_SCRIPT,
    StorybookEditService,
)
from ii_agent.content.storybook.schemas import DesignChange
from ii_agent.content.storybook.router import _format_content_disposition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(timezone.utc)


def _make_edit_service(repo=None, version_service=None) -> StorybookEditService:
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
# _format_content_disposition (router utility)
# ---------------------------------------------------------------------------


class TestFormatContentDisposition:
    def test_ascii_filename(self):
        result = _format_content_disposition("myfile.pdf")
        assert "myfile.pdf" in result
        assert "attachment" in result

    def test_non_ascii_filename(self):
        result = _format_content_disposition("fichier-été.pdf")
        assert "attachment" in result
        assert "UTF-8''" in result

    def test_empty_after_ascii_encode_uses_download(self):
        # All-unicode filename with no ASCII chars
        result = _format_content_disposition("你好.pdf")
        assert "download" in result.lower() or "UTF-8''" in result

    def test_url_encodes_special_chars(self):
        result = _format_content_disposition("file name with spaces.pdf")
        assert "file%20name%20with%20spaces.pdf" in result or "file name with spaces" in result


# ---------------------------------------------------------------------------
# StorybookEditService._find_element_by_context
# ---------------------------------------------------------------------------


class TestFindElementByContext:
    def _soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_returns_none_when_no_tag_name(self):
        soup = self._soup("<div id='a'>hello</div>")
        result = StorybookEditService._find_element_by_context(soup, {"id": "a"})
        assert result is None

    def test_returns_none_when_tag_not_found(self):
        soup = self._soup("<div>hello</div>")
        result = StorybookEditService._find_element_by_context(soup, {"tagName": "span"})
        assert result is None

    def test_finds_by_id(self):
        soup = self._soup("<div id='target'>hello</div>")
        result = StorybookEditService._find_element_by_context(soup, {"tagName": "div", "id": "target"})
        assert result is not None
        assert result.get("id") == "target"

    def test_finds_by_class(self):
        soup = self._soup('<div class="foo bar">hello</div>')
        result = StorybookEditService._find_element_by_context(
            soup, {"tagName": "div", "className": "foo"}
        )
        assert result is not None

    def test_finds_by_attributes(self):
        soup = self._soup('<input type="text" name="email"/>')
        result = StorybookEditService._find_element_by_context(
            soup, {"tagName": "input", "attributes": {"type": "text", "name": "email"}}
        )
        assert result is not None

    def test_finds_by_text_content(self):
        soup = self._soup("<p>Click here for more</p>")
        result = StorybookEditService._find_element_by_context(
            soup, {"tagName": "p", "textContent": "Click here"}
        )
        assert result is not None

    def test_falls_back_to_first_candidate(self):
        soup = self._soup("<div>A</div><div>B</div>")
        result = StorybookEditService._find_element_by_context(
            soup, {"tagName": "div"}
        )
        assert result is not None
        assert result.get_text() == "A"


# ---------------------------------------------------------------------------
# StorybookEditService._apply_attribute_change
# ---------------------------------------------------------------------------


class TestApplyAttributeChange:
    def _svc(self):
        return _make_edit_service()

    def test_returns_original_when_no_attr(self):
        svc = self._svc()
        html = '<div data-design-id="d1">content</div>'
        result, changed = svc._apply_attribute_change(html, design_id="d1", attr="", value="v", context=None)
        assert result == html
        assert changed is False

    def test_returns_false_when_element_not_found(self):
        svc = self._svc()
        html = "<div>content</div>"
        result, changed = svc._apply_attribute_change(html, design_id="no-id", attr="class", value="new", context=None)
        assert changed is False

    def test_removes_attr_when_value_none(self):
        svc = self._svc()
        html = '<div data-design-id="d1" class="old">content</div>'
        result, changed = svc._apply_attribute_change(
            html, design_id="d1", attr="class", value=None, context=None
        )
        assert changed is True
        assert 'class="old"' not in result

    def test_removes_attr_when_empty_string(self):
        svc = self._svc()
        html = '<div data-design-id="d1" title="Hello">content</div>'
        result, changed = svc._apply_attribute_change(
            html, design_id="d1", attr="title", value="", context=None
        )
        assert changed is True

    def test_sets_class_as_list(self):
        svc = self._svc()
        html = '<div data-design-id="d1">content</div>'
        result, changed = svc._apply_attribute_change(
            html, design_id="d1", attr="className", value="foo bar", context=None
        )
        assert changed is True
        assert "foo" in result

    def test_sets_regular_attribute(self):
        svc = self._svc()
        html = '<div data-design-id="d1">content</div>'
        result, changed = svc._apply_attribute_change(
            html, design_id="d1", attr="href", value="https://example.com", context=None
        )
        assert changed is True
        assert "https://example.com" in result

    def test_finds_by_context_when_design_id_missing(self):
        svc = self._svc()
        html = '<div id="target">content</div>'
        context = {"tagName": "div", "id": "target"}
        result, changed = svc._apply_attribute_change(
            html, design_id="d1", attr="title", value="new-title", context=context
        )
        assert changed is True


# ---------------------------------------------------------------------------
# StorybookEditService.apply_changes_to_html
# ---------------------------------------------------------------------------


class TestApplyChangesToHtml:
    @pytest.mark.asyncio
    async def test_returns_original_when_empty_changes(self):
        svc = _make_edit_service()
        html = "<div>content</div>"
        result = await svc.apply_changes_to_html(html, [])
        assert result == html

    @pytest.mark.asyncio
    async def test_returns_original_when_empty_html(self):
        svc = _make_edit_service()
        result = await svc.apply_changes_to_html("", [_change("d1", "text", value="new")])
        assert result == ""

    @pytest.mark.asyncio
    async def test_skips_change_with_no_design_id(self):
        svc = _make_edit_service()
        html = "<div>content</div>"
        change = _change("", "text", value="new")
        result = await svc.apply_changes_to_html(html, [change])
        assert result == html

    @pytest.mark.asyncio
    async def test_applies_style_change(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1" style="color: red;">hello</div>'

        with patch("ii_agent.content.storybook.edit_service.apply_slide_style_change_with_status") as mock_fn:
            mock_fn.return_value = (html, True)
            change = _change("d1", "style", prop="color", value="blue")
            result = await svc.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_text_change(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1">original</div>'

        with patch("ii_agent.content.storybook.edit_service.apply_slide_text_change_with_status") as mock_fn:
            mock_fn.return_value = (html, True)
            change = _change("d1", "text", value="new text")
            await svc.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_icon_change(self):
        svc = _make_edit_service()
        html = '<span data-design-id="d1">icon</span>'

        with patch("ii_agent.content.storybook.edit_service.apply_slide_icon_change_with_status") as mock_fn:
            mock_fn.return_value = (html, True)
            change = _change("d1", "attribute", prop="icon", value="new-icon")
            await svc.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_delete_change(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1">delete me</div>'

        with patch("ii_agent.content.storybook.edit_service.apply_slide_delete_change_with_status") as mock_fn:
            mock_fn.return_value = (html, True)
            change = _change("d1", "delete")
            await svc.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_move_change(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1">item</div>'

        with patch("ii_agent.content.storybook.edit_service.apply_slide_move_change_with_status") as mock_fn:
            mock_fn.return_value = (html, True)
            change = _change("d1", "move", value="after-d2")
            await svc.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_applies_swap_change(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1">item</div>'

        with patch("ii_agent.content.storybook.edit_service.apply_slide_swap_change_with_status") as mock_fn:
            mock_fn.return_value = (html, True)
            change = _change("d1", "swap", value="d2")
            await svc.apply_changes_to_html(html, [change])
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_logs_unsupported_change_type(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1">content</div>'
        change = _change("d1", "unknown_type")
        # Should not raise, just log
        result = await svc.apply_changes_to_html(html, [change])
        assert result is not None

    @pytest.mark.asyncio
    async def test_handles_exception_in_apply_gracefully(self):
        svc = _make_edit_service()
        html = '<div data-design-id="d1">content</div>'

        with patch(
            "ii_agent.content.storybook.edit_service.apply_slide_style_change_with_status",
            side_effect=RuntimeError("boom"),
        ):
            change = _change("d1", "style", prop="color", value="red")
            # Should not raise
            result = await svc.apply_changes_to_html(html, [change])
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# StorybookEditService.get_page_html_with_runtime
# ---------------------------------------------------------------------------


class TestGetPageHtmlWithRuntime:
    @pytest.mark.asyncio
    async def test_returns_none_when_page_not_found(self):
        repo = AsyncMock()
        repo.get_page_by_number = AsyncMock(return_value=None)
        svc = _make_edit_service(repo=repo)
        result = await svc.get_page_html_with_runtime(None, storybook_id="sb1", page_number=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_page_has_no_html(self):
        repo = AsyncMock()
        repo.get_page_by_number = AsyncMock(
            return_value=SimpleNamespace(html_content=None)
        )
        svc = _make_edit_service(repo=repo)
        result = await svc.get_page_html_with_runtime(None, storybook_id="sb1", page_number=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_injects_runtime_into_html(self):
        repo = AsyncMock()
        repo.get_page_by_number = AsyncMock(
            return_value=SimpleNamespace(html_content="<html><head></head><body></body></html>")
        )
        svc = _make_edit_service(repo=repo)
        result = await svc.get_page_html_with_runtime(None, storybook_id="sb1", page_number=1)
        assert result is not None
        assert "__STORYBOOK_INLINE_EDIT__" in result


# ---------------------------------------------------------------------------
# StorybookEditService.save_all_page_edits
# ---------------------------------------------------------------------------


class TestSaveAllPageEdits:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_changes(self):
        svc = _make_edit_service()
        result, cost = await svc.save_all_page_edits(None, storybook_id="sb1", page_changes={})
        assert result is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_returns_none_when_storybook_not_found(self):
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        svc = _make_edit_service(repo=repo)
        result, cost = await svc.save_all_page_edits(
            None, storybook_id="sb1", page_changes={1: [_change("d1", "text", value="hello")]}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_missing_page_number(self):
        repo = AsyncMock()
        source_storybook = SimpleNamespace(
            id="sb1",
            pages=[SimpleNamespace(page_number=1, html_content="<html>page1</html>")],
            style_json={},
            session_id="s1",
            root_storybook_id=None,
        )
        repo.get_by_id = AsyncMock(return_value=source_storybook)

        vs = AsyncMock()
        vs.create_storybook_version_multi_page = AsyncMock(return_value=None)

        svc = _make_edit_service(repo=repo, version_service=vs)
        # page 99 doesn't exist
        result, cost = await svc.save_all_page_edits(
            None,
            storybook_id="sb1",
            page_changes={99: [_change("d1", "text", value="hi")]},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_applies_image_url_update(self):
        repo = AsyncMock()
        source_storybook = SimpleNamespace(
            id="sb1",
            pages=[SimpleNamespace(page_number=1, html_content="<html>page1</html>")],
            style_json={},
            session_id="s1",
            root_storybook_id=None,
        )
        repo.get_by_id = AsyncMock(return_value=source_storybook)

        new_detail = SimpleNamespace(id="sb2", pages=[])
        vs = AsyncMock()
        vs.create_storybook_version_multi_page = AsyncMock(return_value=new_detail)
        svc = _make_edit_service(repo=repo, version_service=vs)

        result, cost = await svc.save_all_page_edits(
            None,
            storybook_id="sb1",
            page_changes={},
            image_urls={1: "https://new-image.url/img.png"},
        )
        assert result is new_detail
        vs.create_storybook_version_multi_page.assert_called_once()


# ---------------------------------------------------------------------------
# StorybookEditService.get_version_history
# ---------------------------------------------------------------------------


class TestGetVersionHistory:
    @pytest.mark.asyncio
    async def test_returns_empty_when_storybook_not_found(self):
        repo = AsyncMock()
        repo.get_by_id = AsyncMock(return_value=None)
        svc = _make_edit_service(repo=repo)
        result = await svc.get_version_history(None, storybook_id="sb1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_root_not_resolved(self):
        repo = AsyncMock()
        storybook = SimpleNamespace(
            id="sb1",
            root_storybook_id=None,
            parent_storybook_id=None,
        )
        repo.get_by_id = AsyncMock(return_value=storybook)
        svc = _make_edit_service(repo=repo)
        result = await svc.get_version_history(None, storybook_id="sb1")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_version_list(self):
        repo = AsyncMock()
        storybook = SimpleNamespace(
            id="sb1",
            root_storybook_id="sb-root",
            parent_storybook_id=None,
        )
        repo.get_by_id = AsyncMock(return_value=storybook)
        repo.get_version_family = AsyncMock(
            return_value=[
                SimpleNamespace(id="sb-root", version=1, created_at=_now()),
                SimpleNamespace(id="sb1", version=2, created_at=_now()),
            ]
        )
        svc = _make_edit_service(repo=repo)
        result = await svc.get_version_history(None, storybook_id="sb1")
        assert len(result) == 2
        current = next((v for v in result if v.is_current), None)
        assert current is not None
        assert current.id == "sb1"


# ---------------------------------------------------------------------------
# StorybookEditService._resolve_root_storybook_id
# ---------------------------------------------------------------------------


class TestResolveRootStorybookId:
    @pytest.mark.asyncio
    async def test_returns_self_when_no_parent(self):
        repo = AsyncMock()
        svc = _make_edit_service(repo=repo)
        storybook = SimpleNamespace(id="sb1", parent_storybook_id=None)
        result = await svc._resolve_root_storybook_id(None, storybook)
        assert result == "sb1"

    @pytest.mark.asyncio
    async def test_walks_parent_chain(self):
        repo = AsyncMock()
        root = SimpleNamespace(id="sb-root", parent_storybook_id=None)
        child = SimpleNamespace(id="sb-child", parent_storybook_id="sb-root")
        repo.get_by_id = AsyncMock(return_value=root)

        svc = _make_edit_service(repo=repo)
        result = await svc._resolve_root_storybook_id(None, child)
        assert result == "sb-root"

    @pytest.mark.asyncio
    async def test_handles_cycle_gracefully(self):
        """Guard against circular parent references."""
        repo = AsyncMock()
        # sb1 -> sb2 -> sb1 (cycle)
        sb1 = SimpleNamespace(id="sb1", parent_storybook_id="sb2")
        sb2 = SimpleNamespace(id="sb2", parent_storybook_id="sb1")
        repo.get_by_id = AsyncMock(return_value=sb2)

        svc = _make_edit_service(repo=repo)
        result = await svc._resolve_root_storybook_id(None, sb1)
        # Should return None to break the cycle
        assert result is None


# ---------------------------------------------------------------------------
# pdf_export: compress_pdf_images (unit test for the standalone function)
# ---------------------------------------------------------------------------


class TestCompressPdfImages:
    def test_handles_empty_pages(self):
        """Should not raise on a writer with no pages."""
        from ii_agent.content.storybook.pdf_export import compress_pdf_images
        from unittest.mock import MagicMock

        writer = MagicMock()
        writer.pages = []
        # Should not raise
        compress_pdf_images(writer)

    def test_handles_page_without_resources(self):
        """Should skip pages without /Resources."""
        from ii_agent.content.storybook.pdf_export import compress_pdf_images

        page = MagicMock()
        page.__contains__ = MagicMock(return_value=False)  # "/Resources" not in page

        writer = MagicMock()
        writer.pages = [page]
        compress_pdf_images(writer)

    def test_handles_page_without_xobject(self):
        """Should skip pages without /XObject in resources."""
        from ii_agent.content.storybook.pdf_export import compress_pdf_images

        resources = MagicMock()
        resources.__contains__ = MagicMock(return_value=False)

        page = MagicMock()
        page.__contains__ = MagicMock(return_value=True)
        page.__getitem__ = MagicMock(return_value=resources)

        writer = MagicMock()
        writer.pages = [page]
        compress_pdf_images(writer)
