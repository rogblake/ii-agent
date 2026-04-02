"""Unit tests for design utils: lucide_catalog, runtime_injector, iframe tools (r4)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# lucide_catalog tests
# ---------------------------------------------------------------------------


class TestLucideCatalogR4:
    """Tests for lucide_catalog helper functions."""

    def test_normalize_icon_name_basic(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        assert _normalize_icon_name("rocket") == "rocket"

    def test_normalize_icon_name_converts_underscores_to_hyphens(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        assert _normalize_icon_name("arrow_up") == "arrow-up"

    def test_normalize_icon_name_converts_spaces_to_hyphens(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        assert _normalize_icon_name("arrow up") == "arrow-up"

    def test_normalize_icon_name_removes_invalid_chars(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        assert _normalize_icon_name("arrow!up") == "arrowup"

    def test_normalize_icon_name_lowercases(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        assert _normalize_icon_name("ArrowUP") == "arrowup"

    def test_normalize_icon_name_empty_returns_empty(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        assert _normalize_icon_name("") == ""

    def test_normalize_icon_name_strips_leading_trailing_hyphens(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        result = _normalize_icon_name("-arrow-")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_normalize_icon_name_collapses_multiple_hyphens(self):
        from ii_agent.projects.design.utils.lucide_catalog import _normalize_icon_name

        result = _normalize_icon_name("arrow--up")
        assert "--" not in result

    def test_camel_to_kebab_empty(self):
        from ii_agent.projects.design.utils.lucide_catalog import _camel_to_kebab

        assert _camel_to_kebab("") == ""

    def test_camel_to_kebab_already_lowercase(self):
        from ii_agent.projects.design.utils.lucide_catalog import _camel_to_kebab

        assert _camel_to_kebab("stroke") == "stroke"

    def test_camel_to_kebab_converts(self):
        from ii_agent.projects.design.utils.lucide_catalog import _camel_to_kebab

        assert _camel_to_kebab("strokeWidth") == "stroke-width"

    def test_camel_to_kebab_multiple(self):
        from ii_agent.projects.design.utils.lucide_catalog import _camel_to_kebab

        result = _camel_to_kebab("viewBoxHeight")
        assert result == "view-box-height"

    def test_list_icons_returns_list(self):
        from ii_agent.projects.design.utils.lucide_catalog import list_icons

        result = list_icons()
        assert isinstance(result, list)

    def test_list_icons_limit_respected(self):
        from ii_agent.projects.design.utils.lucide_catalog import list_icons

        result = list_icons(limit=5)
        assert len(result) <= 5

    def test_list_icons_with_query_filters(self):
        from ii_agent.projects.design.utils.lucide_catalog import (
            list_icons,
            _list_available_icon_names,
        )

        all_names = _list_available_icon_names()
        if not all_names:
            pytest.skip("No icons available in test environment")
        query = all_names[0][:3]  # Use first 3 chars as query
        result = list_icons(query=query, limit=50)
        assert all(query in name for name in result)

    def test_list_icons_limit_bounds_respected(self):
        from ii_agent.projects.design.utils.lucide_catalog import list_icons

        # Limit of 1 should give at most 1 result
        result = list_icons(limit=1)
        assert len(result) <= 1

    def test_list_icons_no_query_returns_up_to_limit(self):
        from ii_agent.projects.design.utils.lucide_catalog import list_icons

        result = list_icons(query=None, limit=10)
        assert len(result) <= 10

    def test_get_icon_svg_inner_returns_string_or_none(self):
        from ii_agent.projects.design.utils.lucide_catalog import get_icon_svg_inner

        result = get_icon_svg_inner("rocket")
        # Either a string or None (if no catalog available)
        assert result is None or isinstance(result, str)

    def test_get_icon_svg_inner_empty_name_returns_none(self):
        from ii_agent.projects.design.utils.lucide_catalog import get_icon_svg_inner

        assert get_icon_svg_inner("") is None

    def test_get_icon_svg_inner_invalid_name_returns_none(self):
        from ii_agent.projects.design.utils.lucide_catalog import get_icon_svg_inner

        result = get_icon_svg_inner("xxxx-definitely-not-an-icon-9999")
        assert result is None

    def test_icon_node_to_svg_inner_returns_none_for_empty(self):
        from ii_agent.projects.design.utils.lucide_catalog import _icon_node_to_svg_inner

        assert _icon_node_to_svg_inner([]) is None

    def test_icon_node_to_svg_inner_returns_string_for_valid(self):
        from ii_agent.projects.design.utils.lucide_catalog import _icon_node_to_svg_inner

        node = [["path", {"d": "M0 0 L10 10", "stroke": "currentColor"}]]
        result = _icon_node_to_svg_inner(node)
        assert result is not None
        assert "<path" in result
        assert "d=" in result

    def test_icon_node_to_svg_inner_skips_invalid_entries(self):
        from ii_agent.projects.design.utils.lucide_catalog import _icon_node_to_svg_inner

        entries = [
            "not_a_list",
            ["too_many", "items", "here"],
            ["circle", {"cx": "12", "cy": "12", "r": "5"}],
        ]
        result = _icon_node_to_svg_inner(entries)
        assert result is not None
        assert "<circle" in result

    def test_icon_node_to_svg_inner_escapes_attributes(self):
        from ii_agent.projects.design.utils.lucide_catalog import _icon_node_to_svg_inner

        node = [["path", {"d": "<>&", "key": "ignored"}]]
        result = _icon_node_to_svg_inner(node)
        assert result is not None
        # key attribute should be excluded
        assert "key" not in result
        # HTML special chars should be escaped
        assert (
            "&lt;" in result
            or "&amp;" in result
            or ">" not in result.replace("<path", "").replace("/>", "")
        )

    def test_parse_icon_node_from_file_returns_none_for_nonexistent(self):
        from pathlib import Path
        from ii_agent.projects.design.utils.lucide_catalog import _parse_icon_node_from_file

        result = _parse_icon_node_from_file(Path("/nonexistent/path.js"))
        assert result is None

    def test_load_catalog_returns_dict(self):
        from ii_agent.projects.design.utils.lucide_catalog import _load_catalog

        result = _load_catalog()
        assert isinstance(result, dict)

    def test_catalog_paths_returns_list(self):
        from ii_agent.projects.design.utils.lucide_catalog import _catalog_paths

        paths = _catalog_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0


# ---------------------------------------------------------------------------
# runtime_injector tests
# ---------------------------------------------------------------------------


class TestRuntimeInjectorR4:
    def test_inject_into_head_tag(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_only

        html = "<html><head></head><body>content</body></html>"
        result = inject_runtime_script_only(html)
        assert len(result) > len(html)
        assert "<head>" in result

    def test_inject_into_head_with_attributes(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_only

        html = '<html><head lang="en"></head><body></body></html>'
        result = inject_runtime_script_only(html)
        assert len(result) > len(html)

    def test_inject_fallback_when_no_head(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_only

        html = "<p>No head here</p>"
        result = inject_runtime_script_only(html)
        assert len(result) > len(html)

    def test_inject_creates_head_when_html_only(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_only

        html = "<html><body>content</body></html>"
        result = inject_runtime_script_only(html)
        assert "<head>" in result

    def test_inject_with_base_url_adds_base_tag(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_with_base

        html = "<html><head></head><body></body></html>"
        result = inject_runtime_script_with_base(html, "https://sandbox.e2b.app/")
        assert "sandbox.e2b.app" in result
        assert "<base" in result

    def test_inject_with_base_url_in_head_attr(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_with_base

        html = '<html><head class="custom"></head><body></body></html>'
        result = inject_runtime_script_with_base(html, "https://example.com/")
        assert "example.com" in result

    def test_inject_with_base_url_no_head_tag(self):
        from ii_agent.projects.design.utils.runtime_injector import inject_runtime_script_with_base

        html = "<p>Bare HTML</p>"
        result = inject_runtime_script_with_base(html, "https://example.com/")
        assert len(result) > len(html)

    def test_sanitize_legacy_no_editable_style_blocks(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        html = "<html><body><p>Content</p></body></html>"
        result = sanitize_legacy_editable_artifacts(html)
        assert result == html

    def test_sanitize_legacy_removes_editable_style(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        html = (
            "<style>.editable { color: red; } #ff6b75 { display: none; }</style><div>Content</div>"
        )
        result = sanitize_legacy_editable_artifacts(html)
        assert "<style>" not in result or ".editable" not in result

    def test_sanitize_legacy_removes_data_edit_id(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        html = '<p data-edit-id="p1">Text</p>'
        result = sanitize_legacy_editable_artifacts(html)
        assert "data-edit-id" not in result

    def test_sanitize_legacy_removes_contenteditable(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        html = '<div contenteditable="true">Edit me</div>'
        result = sanitize_legacy_editable_artifacts(html)
        assert "contenteditable" not in result

    def test_sanitize_legacy_removes_editable_class(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
            EDITABLE_CLASS_NAMES,
        )

        if not EDITABLE_CLASS_NAMES:
            pytest.skip("No editable class names defined")
        cls = next(iter(EDITABLE_CLASS_NAMES))
        html = f'<div class="{cls} other-class">Text</div>'
        result = sanitize_legacy_editable_artifacts(html)
        assert cls not in result

    def test_sanitize_legacy_preserves_non_editable_class(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        html = '<div class="my-custom-class not-editable">Text</div>'
        result = sanitize_legacy_editable_artifacts(html)
        assert "my-custom-class" in result
        assert "not-editable" in result

    def test_sanitize_legacy_empty_html(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        result = sanitize_legacy_editable_artifacts("")
        assert result == ""

    def test_sanitize_legacy_none_like_input(self):
        from ii_agent.projects.design.utils.runtime_injector import (
            sanitize_legacy_editable_artifacts,
        )

        result = sanitize_legacy_editable_artifacts("   ")
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# iframe_list_icons tool tests
# ---------------------------------------------------------------------------


class TestIframeListIconsToolR4:
    def _make_tool(self, max_searches: int = 3):
        from ii_agent.projects.design.tools.iframe_list_icons import DesignModeIframeAIListIconsTool

        return DesignModeIframeAIListIconsTool(max_icon_searches=max_searches)

    def test_tool_name(self):
        tool = self._make_tool()
        assert tool.name == "list_icons"

    def test_tool_info_has_correct_name(self):
        tool = self._make_tool()
        info = tool.info()
        assert info.name == "list_icons"

    def test_tool_info_has_description(self):
        tool = self._make_tool()
        info = tool.info()
        assert info.description

    def test_max_icon_searches_minimum_1(self):
        from ii_agent.projects.design.tools.iframe_list_icons import DesignModeIframeAIListIconsTool

        tool = DesignModeIframeAIListIconsTool(max_icon_searches=0)
        assert tool._max_icon_searches >= 1

    @pytest.mark.asyncio
    async def test_run_returns_icons_list(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = json.dumps({"query": None, "limit": 10})
        response = await tool.run(tool_call)
        assert response is not None
        output_value = response.output.value
        assert "icons" in output_value

    @pytest.mark.asyncio
    async def test_run_with_query_filters_results(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = json.dumps({"query": "arrow", "limit": 20})
        response = await tool.run(tool_call)
        output_value = response.output.value
        assert "icons" in output_value

    @pytest.mark.asyncio
    async def test_run_adds_note_when_max_reached(self):
        tool = self._make_tool(max_searches=1)
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = json.dumps({})
        response = await tool.run(tool_call)
        output_value = response.output.value
        # After first call, max reached
        assert "note" in output_value

    @pytest.mark.asyncio
    async def test_run_invalid_json_returns_error(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = "not valid json {{"
        response = await tool.run(tool_call)
        from ii_agent.chat.types import ErrorTextContent

        assert isinstance(response.output, ErrorTextContent)


# ---------------------------------------------------------------------------
# iframe_get_icon_svg tool tests
# ---------------------------------------------------------------------------


class TestIframeGetIconSvgToolR4:
    def _make_tool(self):
        from ii_agent.projects.design.tools.iframe_get_icon_svg import (
            DesignModeIframeAIGetIconSvgTool,
        )

        return DesignModeIframeAIGetIconSvgTool()

    def test_tool_name(self):
        tool = self._make_tool()
        assert tool.name == "get_icon_svg"

    def test_tool_info_has_correct_name(self):
        tool = self._make_tool()
        info = tool.info()
        assert info.name == "get_icon_svg"

    def test_tool_info_requires_name(self):
        tool = self._make_tool()
        info = tool.info()
        assert "name" in info.required

    @pytest.mark.asyncio
    async def test_run_returns_svg_when_found(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = json.dumps({"name": "rocket"})

        with patch(
            "ii_agent.projects.design.tools.iframe_get_icon_svg.lucide_catalog.get_icon_svg_inner",
            return_value='<circle cx="12" cy="12" r="5"/>',
        ):
            response = await tool.run(tool_call)
        output_value = response.output.value
        assert "svg_inner" in output_value
        assert "<circle" in output_value["svg_inner"]

    @pytest.mark.asyncio
    async def test_run_returns_suggestions_when_not_found(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = json.dumps({"name": "nonexistent-icon-xyz"})

        with (
            patch(
                "ii_agent.projects.design.tools.iframe_get_icon_svg.lucide_catalog.get_icon_svg_inner",
                return_value=None,
            ),
            patch(
                "ii_agent.projects.design.tools.iframe_get_icon_svg.lucide_catalog.list_icons",
                return_value=["arrow-up", "arrow-down"],
            ),
        ):
            response = await tool.run(tool_call)
        output_value = response.output.value
        assert "error" in output_value
        assert output_value["error"] == "not_found"
        assert "suggestions" in output_value

    @pytest.mark.asyncio
    async def test_run_invalid_json_returns_error(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = "{{not valid json"
        response = await tool.run(tool_call)
        from ii_agent.chat.types import ErrorTextContent

        assert isinstance(response.output, ErrorTextContent)

    @pytest.mark.asyncio
    async def test_run_catalog_exception_handled(self):
        tool = self._make_tool()
        tool_call = MagicMock()
        tool_call.id = "tc-1"
        tool_call.input = json.dumps({"name": "rocket"})

        with (
            patch(
                "ii_agent.projects.design.tools.iframe_get_icon_svg.lucide_catalog.get_icon_svg_inner",
                side_effect=Exception("catalog error"),
            ),
            patch(
                "ii_agent.projects.design.tools.iframe_get_icon_svg.lucide_catalog.list_icons",
                return_value=["fallback-icon"],
            ),
        ):
            response = await tool.run(tool_call)
        # Should not raise, should return suggestions
        assert response is not None
