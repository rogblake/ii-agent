"""Tests for _constants.py."""

from ii_agent.design.source_mapping_sync._constants import (
    DESIGN_MODE_MANIFEST_FILENAME,
    _DESIGN_MODE_CSS_OVERRIDES_END,
    _DESIGN_MODE_CSS_OVERRIDES_START,
    _DESIGN_MODE_HTML_TAG_NAMES,
    _truncate_for_log,
)


class TestTruncateForLog:
    def test_short_string_unchanged(self):
        assert _truncate_for_log("hello") == "hello"

    def test_exact_limit_unchanged(self):
        value = "x" * 4000
        assert _truncate_for_log(value) == value

    def test_over_limit_truncated(self):
        value = "x" * 4001
        result = _truncate_for_log(value)
        assert result.endswith("\n...[truncated]")
        assert result != value
        assert result.startswith("x" * 4000)

    def test_custom_limit(self):
        value = "abcdefgh"
        result = _truncate_for_log(value, limit=3)
        assert result == "abc\n...[truncated]"


class TestConstantsSmoke:
    def test_manifest_filename_exists(self):
        assert DESIGN_MODE_MANIFEST_FILENAME == "design-mode.manifest.json"

    def test_css_markers_exist(self):
        assert isinstance(_DESIGN_MODE_CSS_OVERRIDES_START, str)
        assert isinstance(_DESIGN_MODE_CSS_OVERRIDES_END, str)
        assert "Design Mode" in _DESIGN_MODE_CSS_OVERRIDES_START
        assert "End Design Mode" in _DESIGN_MODE_CSS_OVERRIDES_END

    def test_html_tag_set_contains_common_tags(self):
        assert "div" in _DESIGN_MODE_HTML_TAG_NAMES
        assert "span" in _DESIGN_MODE_HTML_TAG_NAMES
        assert "svg" in _DESIGN_MODE_HTML_TAG_NAMES
        assert "path" in _DESIGN_MODE_HTML_TAG_NAMES
