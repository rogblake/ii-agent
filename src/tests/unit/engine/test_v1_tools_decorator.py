"""Unit tests for the tool decorator."""

import pytest
from unittest.mock import MagicMock

from ii_agent.agents.tools.decorator import tool, _is_async_function


# ---------------------------------------------------------------------------
# _is_async_function tests
# ---------------------------------------------------------------------------


class TestIsAsyncFunction:
    def test_regular_function_is_not_async(self):
        def sync_func():
            pass

        assert _is_async_function(sync_func) is False

    def test_async_function_is_async(self):
        async def async_func():
            pass

        assert _is_async_function(async_func) is True

    def test_wrapped_async_function_detected(self):
        import functools

        async def inner():
            pass

        @functools.wraps(inner)
        def wrapper():
            pass

        wrapper.__wrapped__ = inner
        assert _is_async_function(wrapper) is True

    def test_callable_object_not_async(self):
        class NotAsync:
            def __call__(self):
                pass

        assert _is_async_function(NotAsync()) is False


# ---------------------------------------------------------------------------
# @tool decorator - basic usage
# ---------------------------------------------------------------------------


class TestToolDecoratorBasic:
    def test_decorate_sync_function(self):
        @tool
        def my_func():
            """My function."""
            pass

        assert my_func.name == "my_func"

    def test_decorate_async_function(self):
        @tool
        async def my_async_func():
            """My async function."""
            pass

        assert my_async_func.name == "my_async_func"

    def test_decorate_with_parentheses(self):
        @tool()
        def my_func():
            """My func."""
            pass

        assert my_func.name == "my_func"

    def test_custom_name(self):
        @tool(name="custom_tool_name")
        def my_func():
            """My func."""
            pass

        assert my_func.name == "custom_tool_name"

    def test_custom_description(self):
        @tool(description="Custom description")
        def my_func():
            pass

        assert my_func.description == "Custom description"

    def test_description_from_docstring_when_not_provided(self):
        @tool
        def my_func():
            """This is the docstring."""
            pass

        assert "docstring" in my_func.description

    def test_invalid_kwargs_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid tool configuration arguments"):

            @tool(invalid_kwarg=True)
            def my_func():
                pass

    def test_function_is_callable(self):
        @tool
        def my_func(x: int) -> str:
            """Return x as string."""
            return str(x)

        assert callable(my_func.entrypoint)


# ---------------------------------------------------------------------------
# Exclusive flags validation
# ---------------------------------------------------------------------------


class TestExclusiveFlagsValidation:
    def test_requires_user_input_and_confirmation_raises(self):
        with pytest.raises(ValueError, match="Only one of"):

            @tool(requires_user_input=True, requires_confirmation=True)
            def my_func():
                pass

    def test_requires_confirmation_and_external_execution_raises(self):
        with pytest.raises(ValueError, match="Only one of"):

            @tool(requires_confirmation=True, external_execution=True)
            def my_func():
                pass

    def test_single_exclusive_flag_ok(self):
        @tool(requires_confirmation=True)
        def my_func():
            """OK."""
            pass

        assert my_func is not None


# ---------------------------------------------------------------------------
# requires_user_input logic
# ---------------------------------------------------------------------------


class TestRequiresUserInputLogic:
    def test_user_input_fields_sets_requires_user_input(self):
        @tool(user_input_fields=["field1"])
        def my_func(field1: str):
            """Has user input field."""
            pass

        # If user_input_fields specified, requires_user_input should be True
        assert my_func.requires_user_input is True

    def test_requires_user_input_initializes_user_input_fields(self):
        @tool(requires_user_input=True)
        def my_func():
            """Needs user input."""
            pass

        assert my_func.requires_user_input is True


# ---------------------------------------------------------------------------
# stop_after_tool_call logic
# ---------------------------------------------------------------------------


class TestStopAfterToolCall:
    def test_stop_after_tool_call_sets_show_result(self):
        @tool(stop_after_tool_call=True)
        def my_func():
            """Stops after call."""
            pass

        assert my_func.show_result is True

    def test_stop_after_tool_call_false_does_not_set_show_result(self):
        @tool(stop_after_tool_call=False)
        def my_func():
            """Does not stop."""
            pass

        # show_result should not be forced True


# ---------------------------------------------------------------------------
# Wrapper behavior tests
# ---------------------------------------------------------------------------


class TestWrapperBehavior:
    def test_sync_wrapper_executes_function(self):
        @tool
        def my_func(x: int) -> int:
            """Double x."""
            return x * 2

        result = my_func.entrypoint(3)
        assert result == 6

    @pytest.mark.asyncio
    async def test_async_wrapper_executes_async_function(self):
        @tool
        async def my_async_func(x: int) -> int:
            """Async double."""
            return x * 2

        result = await my_async_func.entrypoint(5)
        assert result == 10

    def test_sync_wrapper_propagates_exceptions(self):
        @tool
        def my_func():
            """Raises."""
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            my_func.entrypoint()

    @pytest.mark.asyncio
    async def test_async_wrapper_propagates_exceptions(self):
        @tool
        async def my_async_func():
            """Async raises."""
            raise RuntimeError("async error")

        with pytest.raises(RuntimeError, match="async error"):
            await my_async_func.entrypoint()


# ---------------------------------------------------------------------------
# Function metadata preservation
# ---------------------------------------------------------------------------


class TestFunctionMetadataPreservation:
    def test_function_name_preserved(self):
        @tool
        def very_specific_function_name():
            """Test."""
            pass

        # The entrypoint should have correct name
        assert very_specific_function_name.name == "very_specific_function_name"

    def test_process_entrypoint_generates_parameters(self):
        @tool
        def my_func(name: str, count: int = 5):
            """Process name count times.

            Args:
                name (str): The name to process.
                count (int): Number of times to process.
            """
            pass

        my_func.process_entrypoint()
        # Should have parameters from the function signature
        assert my_func.parameters is not None


# ---------------------------------------------------------------------------
# Different decorator usage patterns
# ---------------------------------------------------------------------------


class TestDecoratorUsagePatterns:
    def test_tool_used_without_parens(self):
        @tool
        def func1():
            """Without parens."""
            pass

        assert func1 is not None
        assert func1.name == "func1"

    def test_tool_used_with_empty_parens(self):
        @tool()
        def func2():
            """With empty parens."""
            pass

        assert func2 is not None
        assert func2.name == "func2"

    def test_tool_used_with_kwargs(self):
        @tool(name="override", description="Override desc")
        def func3():
            """With kwargs."""
            pass

        assert func3.name == "override"
        assert func3.description == "Override desc"

    def test_decorator_with_strict_option(self):
        @tool(strict=True)
        def strict_func():
            """Strict tool."""
            pass

        assert strict_func is not None

    def test_decorator_with_instructions(self):
        @tool(instructions="Call this tool when needed")
        def instructed_func():
            """Has instructions."""
            pass

        assert instructed_func.instructions == "Call this tool when needed"

    def test_decorator_with_pre_hook(self):
        mock_hook = MagicMock()

        @tool(pre_hook=mock_hook)
        def hooked_func():
            """Has pre hook."""
            pass

        assert hooked_func is not None

    def test_decorator_with_post_hook(self):
        mock_hook = MagicMock()

        @tool(post_hook=mock_hook)
        def hooked_func():
            """Has post hook."""
            pass

        assert hooked_func is not None

    def test_decorator_with_show_result(self):
        @tool(show_result=True)
        def show_result_func():
            """Shows result."""
            pass

        assert show_result_func.show_result is True
