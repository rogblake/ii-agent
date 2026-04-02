from ii_agent.utils.indent_utils import (
    IndentType,
    apply_indent_type,
    detect_indent_type,
    force_normalize_indent,
    normalize_indent,
)


def test_detect_indent_type_space_and_mixed():
    space_code = "if True:\n    x = 1\n    y = 2\n"
    mixed_code = "if True:\n\tx = 1\n    y = 2\n"

    assert detect_indent_type(space_code) == IndentType.space(4)
    assert detect_indent_type(mixed_code).is_mixed is True


def test_normalize_indent_from_tabs_to_spaces():
    code = "if True:\n\tvalue = 1\n\treturn value\n"

    normalized = normalize_indent(code, IndentType.tab())

    assert "\t" not in normalized
    assert "    value = 1" in normalized


def test_apply_indent_type_from_spaces_to_tabs_preserves_structure():
    code = "if True:\n    value = 1\n    return value\n"

    retabbed = apply_indent_type(code, IndentType.tab(), IndentType.space(4))

    assert "\tvalue = 1" in retabbed
    assert "\treturn value" in retabbed


def test_force_normalize_indent_handles_mixed_indentation():
    code = "if True:\n\t x = 1\n"

    normalized = force_normalize_indent(code)

    assert normalized.startswith("if True")
    assert "\t" not in normalized
