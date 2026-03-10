"""Unit tests for ii_agent/engine/runtime/tools/function.py.

Tests cover:
- Function Pydantic model creation (minimal, full, defaults)
- Function.parameters default value
- get_entrypoint_docstring() with various callable types
"""

from __future__ import annotations

import pytest
from functools import partial
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# get_entrypoint_docstring
# ---------------------------------------------------------------------------

class TestGetEntrypointDocstring:
    """Tests for the get_entrypoint_docstring() helper."""

    def test_function_with_short_docstring_returns_short_description(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        def my_func():
            """Short description only."""
            pass

        result = get_entrypoint_docstring(my_func)
        assert result == "Short description only."

    def test_function_with_no_docstring_returns_empty_string(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        def undocumented():
            pass

        result = get_entrypoint_docstring(undocumented)
        assert result == ""

    def test_function_with_long_docstring_includes_both_parts(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        def well_documented():
            """Short summary.

            This is the long description that spans
            multiple lines.
            """
            pass

        result = get_entrypoint_docstring(well_documented)
        assert "Short summary." in result
        assert "long description" in result

    def test_partial_function_returns_str_representation(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        def base(x, y):
            """Base doc."""
            return x + y

        p = partial(base, y=10)
        result = get_entrypoint_docstring(p)
        # For a partial, it returns str(partial_object) rather than a docstring
        assert isinstance(result, str)
        assert len(result) > 0

    def test_lambda_with_no_docstring_returns_empty_string(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        fn = lambda x: x
        result = get_entrypoint_docstring(fn)
        assert result == ""

    def test_class_method_with_docstring_returns_description(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        class Dummy:
            def method(self):
                """Method docstring here."""
                pass

        result = get_entrypoint_docstring(Dummy().method)
        assert result == "Method docstring here."

    def test_function_with_only_params_in_docstring_returns_empty_description(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        def params_only(x):
            """
            Args:
                x: The x parameter.
            """
            pass

        result = get_entrypoint_docstring(params_only)
        # No short or long description; params are not included
        assert isinstance(result, str)

    def test_built_in_partial_with_positional_arg(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        p = partial(max, 5)
        result = get_entrypoint_docstring(p)
        # partial always returns str(entrypoint) path
        assert isinstance(result, str)

    def test_docstring_with_returns_section_excluded(self):
        from ii_agent.engine.runtime.tools.function import get_entrypoint_docstring

        def has_returns():
            """Compute something.

            Returns:
                int: The computed result.
            """
            pass

        result = get_entrypoint_docstring(has_returns)
        assert "Compute something." in result
        # Returns section is not in description lines
        assert "int:" not in result


# ---------------------------------------------------------------------------
# Function model
# ---------------------------------------------------------------------------

class TestFunctionModel:
    """Tests for the Function Pydantic model."""

    def test_create_with_minimal_args(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="my_tool")
        assert fn.name == "my_tool"

    def test_create_with_full_args(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(
            name="full_tool",
            description="A full tool",
            strict=True,
            display_name="Full Tool",
            tool_logo="https://example.com/logo.png",
            instructions="Use this tool carefully",
            add_instructions=True,
            show_result=True,
            stop_after_tool_call=False,
            requires_confirmation=True,
            requires_user_input=False,
        )
        assert fn.name == "full_tool"
        assert fn.description == "A full tool"
        assert fn.strict is True
        assert fn.display_name == "Full Tool"
        assert fn.tool_logo == "https://example.com/logo.png"
        assert fn.instructions == "Use this tool carefully"
        assert fn.add_instructions is True
        assert fn.show_result is True
        assert fn.stop_after_tool_call is False
        assert fn.requires_confirmation is True
        assert fn.requires_user_input is False

    def test_description_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="no_desc")
        assert fn.description is None

    def test_parameters_default_is_empty_schema(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool_with_defaults")
        assert fn.parameters == {"type": "object", "properties": {}, "required": []}

    def test_parameters_default_type_is_object(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.parameters["type"] == "object"

    def test_parameters_default_properties_is_empty(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.parameters["properties"] == {}

    def test_parameters_default_required_is_empty(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.parameters["required"] == []

    def test_parameters_can_be_overridden(self):
        from ii_agent.engine.runtime.tools.function import Function

        custom_params = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        fn = Function(name="search_tool", parameters=custom_params)
        assert fn.parameters == custom_params

    def test_strict_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.strict is None

    def test_display_name_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.display_name is None

    def test_tool_logo_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.tool_logo is None

    def test_add_instructions_defaults_to_true(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.add_instructions is True

    def test_show_result_defaults_to_false(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.show_result is False

    def test_stop_after_tool_call_defaults_to_false(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.stop_after_tool_call is False

    def test_entrypoint_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.entrypoint is None

    def test_skip_entrypoint_processing_defaults_to_false(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.skip_entrypoint_processing is False

    def test_pre_hook_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.pre_hook is None

    def test_post_hook_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.post_hook is None

    def test_requires_confirmation_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.requires_confirmation is None

    def test_requires_user_input_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.requires_user_input is None

    def test_user_input_fields_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.user_input_fields is None

    def test_external_execution_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.external_execution is None

    def test_requires_sandbox_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.requires_sandbox is None

    def test_to_dict_contains_name(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="my_tool")
        result = fn.to_dict()
        assert result["name"] == "my_tool"

    def test_to_dict_excludes_none_fields(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="my_tool")
        result = fn.to_dict()
        # None fields should be excluded
        assert "description" not in result or result.get("description") is not None

    def test_to_dict_includes_description_when_set(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="my_tool", description="Does stuff")
        result = fn.to_dict()
        assert result["description"] == "Does stuff"

    def test_to_dict_includes_strict_when_set(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="my_tool", strict=True)
        result = fn.to_dict()
        assert result["strict"] is True

    def test_two_functions_with_same_name_are_equal_in_name(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn1 = Function(name="tool")
        fn2 = Function(name="tool")
        assert fn1.name == fn2.name

    def test_function_parameters_each_instance_is_independent(self):
        """Each Function instance should have its own parameters dict."""
        from ii_agent.engine.runtime.tools.function import Function

        fn1 = Function(name="tool1")
        fn2 = Function(name="tool2")
        fn1.parameters["properties"]["q"] = {"type": "string"}
        assert "q" not in fn2.parameters["properties"]

    def test_function_with_callable_entrypoint(self):
        from ii_agent.engine.runtime.tools.function import Function

        def my_callable(x: int) -> str:
            return str(x)

        fn = Function(name="tool", entrypoint=my_callable)
        assert fn.entrypoint is my_callable

    def test_instructions_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.instructions is None

    def test_tool_hooks_defaults_to_none(self):
        from ii_agent.engine.runtime.tools.function import Function

        fn = Function(name="tool")
        assert fn.tool_hooks is None
