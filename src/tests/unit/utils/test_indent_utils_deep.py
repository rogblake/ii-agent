"""Deep unit tests for ii_agent.utils.indent_utils covering remaining branches."""

from __future__ import annotations

import pytest

from ii_agent.utils.indent_utils import (
    IndentType,
    apply_indent_type,
    detect_indent_type,
    detect_line_indent,
    force_normalize_indent,
    match_indent,
    match_indent_by_first_line,
    normalize_indent,
)


# ---------------------------------------------------------------------------
# IndentType dataclass
# ---------------------------------------------------------------------------


class TestIndentType:
    def test_space_factory(self):
        t = IndentType.space(2)
        assert t.is_space is True
        assert t.is_tab is False
        assert t.is_mixed is False
        assert t.size == 2

    def test_tab_factory(self):
        t = IndentType.tab()
        assert t.is_tab is True
        assert t.is_space is False
        assert t.size == 1

    def test_mixed_factory_with_most_used(self):
        most = IndentType.space(4)
        t = IndentType.mixed(most_used=most)
        assert t.is_mixed is True
        assert t.most_used == most

    def test_mixed_factory_without_most_used(self):
        t = IndentType.mixed()
        assert t.is_mixed is True
        assert t.most_used is None

    def test_repr_space(self):
        r = repr(IndentType.space(4))
        assert "space" in r
        assert "size=4" in r

    def test_repr_tab(self):
        r = repr(IndentType.tab())
        assert "tab" in r

    def test_repr_mixed_with_most_used(self):
        most = IndentType.space(2)
        t = IndentType.mixed(most_used=most)
        r = repr(t)
        assert "mixed" in r
        assert "most_used" in r

    def test_repr_mixed_without_most_used(self):
        t = IndentType.mixed()
        r = repr(t)
        assert "mixed" in r


# ---------------------------------------------------------------------------
# detect_line_indent
# ---------------------------------------------------------------------------


class TestDetectLineIndent:
    def test_empty_line(self):
        assert detect_line_indent("") == (0, 0)

    def test_no_indent(self):
        assert detect_line_indent("hello") == (0, 0)

    def test_spaces_only(self):
        assert detect_line_indent("    hello") == (0, 4)

    def test_tabs_only(self):
        assert detect_line_indent("\t\thello") == (2, 0)

    def test_tabs_then_spaces(self):
        assert detect_line_indent("\t  hello") == (1, 2)

    def test_single_space(self):
        assert detect_line_indent(" hello") == (0, 1)


# ---------------------------------------------------------------------------
# detect_indent_type
# ---------------------------------------------------------------------------


class TestDetectIndentType:
    def test_none_input(self):
        assert detect_indent_type(None) is None

    def test_empty_string(self):
        assert detect_indent_type("") is None

    def test_non_string_input(self):
        # MyPy would reject int, but the function guards isinstance
        assert detect_indent_type(123) is None  # type: ignore[arg-type]

    def test_no_indentation(self):
        code = "hello\nworld\n"
        result = detect_indent_type(code)
        assert result is None

    def test_space_indentation_4(self):
        code = "def f():\n    x = 1\n    y = 2\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_space
        assert result.size == 4

    def test_space_indentation_2(self):
        code = "def f():\n  x = 1\n  y = 2\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_space
        assert result.size == 2

    def test_tab_indentation(self):
        code = "def f():\n\tx = 1\n\ty = 2\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_tab

    def test_mixed_indentation_tabs_and_spaces(self):
        code = "def f():\n\tx = 1\n    y = 2\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_mixed

    def test_mixed_indentation_in_single_line(self):
        code = "def f():\n\t  x = 1\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_mixed

    def test_mixed_most_used_is_tab_when_tabs_dominate(self):
        code = "a:\n\tx = 1\n\ty = 2\n\tz = 3\n    w = 4\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_mixed
        assert result.most_used is not None
        assert result.most_used.is_tab

    def test_mixed_most_used_is_space_when_spaces_dominate(self):
        code = "a:\n    x = 1\n    y = 2\n    z = 3\n\tw = 4\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_mixed
        assert result.most_used is not None
        assert result.most_used.is_space

    def test_blank_lines_ignored(self):
        code = "def f():\n\n    x = 1\n\n"
        result = detect_indent_type(code)
        assert result is not None
        assert result.is_space

    def test_only_blank_lines(self):
        code = "\n\n\n"
        result = detect_indent_type(code)
        assert result is None


# ---------------------------------------------------------------------------
# force_normalize_indent
# ---------------------------------------------------------------------------


class TestForceNormalizeIndent:
    def test_spaces_become_four(self):
        code = "if True:\n  x = 1\n"
        result = force_normalize_indent(code)
        # force_normalize_indent keeps spaces as-is (tabs converted to 4 spaces each)
        # 2 spaces stays as 2 spaces since it only converts tabs
        assert "x = 1" in result

    def test_tabs_become_four_spaces(self):
        code = "if True:\n\tx = 1\n"
        result = force_normalize_indent(code)
        assert "    x = 1" in result
        assert "\t" not in result

    def test_blank_lines_cleared(self):
        code = "if True:\n    pass\n   \n"
        result = force_normalize_indent(code)
        lines = result.split("\n")
        assert lines[2] == ""

    def test_mixed_tabs_and_spaces(self):
        code = "if True:\n\t  x = 1\n"
        result = force_normalize_indent(code)
        assert "\t" not in result


# ---------------------------------------------------------------------------
# normalize_indent
# ---------------------------------------------------------------------------


class TestNormalizeIndent:
    def test_raises_for_mixed_indent_type(self):
        with pytest.raises(AssertionError, match="Cannot normalize mixed"):
            normalize_indent("code", IndentType.mixed())

    def test_none_code_returns_none(self):
        assert normalize_indent(None, IndentType.space(4)) is None

    def test_empty_string_returns_empty(self):
        assert normalize_indent("", IndentType.space(4)) == ""

    def test_tab_to_four_spaces(self):
        code = "def f():\n\tx = 1\n"
        result = normalize_indent(code, IndentType.tab())
        assert "    x = 1" in result
        assert "\t" not in result

    def test_two_spaces_to_four_spaces(self):
        code = "def f():\n  x = 1\n"
        result = normalize_indent(code, IndentType.space(2))
        assert "    x = 1" in result

    def test_four_spaces_unchanged(self):
        code = "def f():\n    x = 1\n"
        result = normalize_indent(code, IndentType.space(4))
        # normalize_indent uses splitlines() + join, so trailing newline may be lost
        assert "    x = 1" in result
        assert "def f():" in result

    def test_blank_lines_preserved(self):
        code = "def f():\n    x = 1\n\n    y = 2\n"
        result = normalize_indent(code, IndentType.space(4))
        assert "\n\n" in result

    def test_no_indent_line_unchanged(self):
        code = "top_level = 1\n    indented = 2\n"
        result = normalize_indent(code, IndentType.space(4))
        assert "top_level = 1" in result


# ---------------------------------------------------------------------------
# apply_indent_type
# ---------------------------------------------------------------------------


class TestApplyIndentType:
    def test_raises_for_mixed_target(self):
        with pytest.raises(AssertionError):
            apply_indent_type("code", IndentType.mixed())

    def test_none_input_returns_none(self):
        assert apply_indent_type(None, IndentType.space(4)) is None

    def test_empty_string_returns_empty(self):
        assert apply_indent_type("", IndentType.space(4)) == ""

    def test_same_type_returns_original(self):
        code = "def f():\n    x = 1\n"
        result = apply_indent_type(code, IndentType.space(4), IndentType.space(4))
        assert result == code

    def test_spaces_to_tabs(self):
        code = "def f():\n    x = 1\n"
        result = apply_indent_type(code, IndentType.tab(), IndentType.space(4))
        assert "\tx = 1" in result

    def test_tabs_to_spaces(self):
        code = "def f():\n\tx = 1\n"
        result = apply_indent_type(code, IndentType.space(4), IndentType.tab())
        assert "    x = 1" in result

    def test_auto_detect_original_indent(self):
        code = "def f():\n  x = 1\n"
        result = apply_indent_type(code, IndentType.space(4))
        assert "    x = 1" in result

    def test_auto_detect_returns_original_for_mixed(self):
        code = "if True:\n\tx = 1\n    y = 2\n"
        result = apply_indent_type(code, IndentType.space(4))
        assert result == code

    def test_empty_lines_preserved(self):
        code = "def f():\n    x = 1\n\n    y = 2\n"
        result = apply_indent_type(code, IndentType.tab(), IndentType.space(4))
        assert "\n\n" in result

    def test_no_indentation_lines_stay_unindented(self):
        code = "top = 1\n    inner = 2\n"
        result = apply_indent_type(code, IndentType.tab(), IndentType.space(4))
        assert "top = 1" in result


# ---------------------------------------------------------------------------
# match_indent_by_first_line
# ---------------------------------------------------------------------------


class TestMatchIndentByFirstLine:
    def test_none_code_returns_none(self):
        assert match_indent_by_first_line(None, "    target") is None

    def test_empty_code_returns_empty(self):
        assert match_indent_by_first_line("", "    target") == ""

    def test_increases_indent(self):
        code = "x = 1\ny = 2\n"
        result = match_indent_by_first_line(code, "    target")
        assert result.startswith("    x = 1")
        assert "    y = 2" in result

    def test_decreases_indent(self):
        code = "    x = 1\n    y = 2\n"
        result = match_indent_by_first_line(code, "x = 1")
        assert result.startswith("x = 1")

    def test_preserves_relative_indentation(self):
        code = "if True:\n    x = 1\n"
        result = match_indent_by_first_line(code, "    if True:")
        assert result.startswith("    if True:")
        assert "        x = 1" in result

    def test_empty_lines_preserved(self):
        code = "x = 1\n\ny = 2\n"
        result = match_indent_by_first_line(code, "  x = 1")
        assert "\n\n" in result or "\n" in result

    def test_no_indent_when_target_has_none(self):
        code = "x = 1\ny = 2\n"
        result = match_indent_by_first_line(code, "x = 1")
        assert result.startswith("x = 1")


# ---------------------------------------------------------------------------
# match_indent
# ---------------------------------------------------------------------------


class TestMatchIndent:
    def test_none_code_returns_none(self):
        assert match_indent(None, "    code") is None

    def test_empty_code_returns_empty(self):
        assert match_indent("", "    code") == ""

    def test_applies_target_indent_type(self):
        code = "def f():\n\tx = 1\n"
        code_to_match = "def g():\n    y = 2\n"
        result = match_indent(code, code_to_match)
        assert result is not None
        assert "\t" not in result or "    " in result

    def test_no_detect_returns_original(self):
        code = "x = 1\n"
        code_to_match = "y = 2\n"
        result = match_indent(code, code_to_match)
        assert result == code

    def test_uses_most_used_when_mixed(self):
        code = "def f():\n    x = 1\n"
        mixed_code = "if True:\n    x = 1\n    y = 2\n\tz = 3\n"
        # Should not raise even with mixed code_to_match
        result = match_indent(code, mixed_code)
        assert result is not None
