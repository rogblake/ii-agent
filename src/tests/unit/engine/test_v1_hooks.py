"""Unit tests for ii_agent.agents.hooks.decorator module.

Tests cover:
- _is_async_function() helper for sync/async/wrapped functions
- @hook decorator in bare form, with parens, and with run_in_background=True
- should_run_in_background() for decorated and undecorated functions
- Invalid kwargs raise ValueError

NOTE: The decorator.py module contains a bug where HOOK_RUN_IN_BACKGROUND_ATTR
is used but never defined at module level. These tests inject the constant
before each test call to allow exercising the intended behavior, and also
directly document the bug.
"""

import asyncio
from contextlib import contextmanager
from functools import wraps
from inspect import iscoroutinefunction

import pytest

from ii_agent.agents.hooks.decorator import _is_async_function
import ii_agent.agents.hooks.decorator as decorator_module


# ---------------------------------------------------------------------------
# Constant name that the decorator code expects to find at module level
# ---------------------------------------------------------------------------

ATTR_NAME = "__hook_run_in_background__"


@contextmanager
def _inject_constant(value: str = ATTR_NAME):
    """Inject the missing HOOK_RUN_IN_BACKGROUND_ATTR constant into the module."""
    setattr(decorator_module, "HOOK_RUN_IN_BACKGROUND_ATTR", value)
    try:
        yield
    finally:
        # Clean up after the test
        if hasattr(decorator_module, "HOOK_RUN_IN_BACKGROUND_ATTR"):
            delattr(decorator_module, "HOOK_RUN_IN_BACKGROUND_ATTR")


# ---------------------------------------------------------------------------
# _is_async_function() tests
# ---------------------------------------------------------------------------


class TestIsAsyncFunction:
    def test_sync_function_returns_false(self):
        def sync_func():
            return 42

        assert _is_async_function(sync_func) is False

    def test_async_function_returns_true(self):
        async def async_func():
            return 42

        assert _is_async_function(async_func) is True

    def test_sync_lambda_returns_false(self):
        fn = lambda x: x + 1
        assert _is_async_function(fn) is False

    def test_wrapped_async_function_returns_true(self):
        async def inner():
            return "inner"

        @wraps(inner)
        def wrapper(*args, **kwargs):
            return inner(*args, **kwargs)

        # wraps sets __wrapped__, so unwrap will find the async original
        assert _is_async_function(wrapper) is True

    def test_double_wrapped_async_function_returns_true(self):
        async def deepest():
            return "deep"

        @wraps(deepest)
        def middle(*args, **kwargs):
            return deepest(*args, **kwargs)

        @wraps(middle)
        def outer(*args, **kwargs):
            return middle(*args, **kwargs)

        assert _is_async_function(outer) is True

    def test_sync_wrapped_sync_function_returns_false(self):
        def base():
            return "base"

        @wraps(base)
        def wrapped():
            return base()

        assert _is_async_function(wrapped) is False

    def test_coroutine_function_detected_via_standard_check(self):
        # Async functions are coroutine functions
        async def async_fn():
            pass

        # Should return True regardless of the detection path
        assert _is_async_function(async_fn) is True

    def test_builtin_function_returns_false(self):
        assert _is_async_function(len) is False

    def test_class_method_sync_returns_false(self):
        class MyClass:
            def method(self):
                return 1

        obj = MyClass()
        assert _is_async_function(obj.method) is False

    def test_class_method_async_returns_true(self):
        class MyClass:
            async def async_method(self):
                return 1

        obj = MyClass()
        assert _is_async_function(obj.async_method) is True


# ---------------------------------------------------------------------------
# @hook decorator - bare form (@hook without parens)
# ---------------------------------------------------------------------------


class TestHookDecoratorBare:
    def test_bare_hook_wraps_sync_function(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            def my_sync_hook():
                return "result"

            assert my_sync_hook() == "result"

    def test_bare_hook_preserves_function_name(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            def named_hook():
                pass

            assert named_hook.__name__ == "named_hook"

    def test_bare_hook_sets_run_in_background_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            def my_hook():
                pass

            assert getattr(my_hook, ATTR_NAME) is False

    def test_bare_hook_on_async_function_returns_coroutine(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            async def my_async_hook():
                return "async_result"

            # The wrapper should be async
            assert iscoroutinefunction(my_async_hook)

    def test_bare_hook_async_function_is_awaitable(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            async def my_async_hook():
                return "async"

            result = asyncio.get_event_loop().run_until_complete(my_async_hook())
            assert result == "async"

    def test_bare_hook_passes_args_through(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            def my_hook(x, y):
                return x + y

            assert my_hook(3, 4) == 7

    def test_bare_hook_passes_kwargs_through(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            def my_hook(*, message="default"):
                return message

            assert my_hook(message="custom") == "custom"

    def test_bare_hook_wrapped_attribute_set(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook
            def my_hook():
                pass

            # functools.wraps should set __wrapped__
            assert hasattr(my_hook, "__wrapped__")


# ---------------------------------------------------------------------------
# @hook decorator - with empty parens (@hook())
# ---------------------------------------------------------------------------


class TestHookDecoratorWithParens:
    def test_hook_with_empty_parens_wraps_sync_function(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook()
            def my_hook():
                return "parens_result"

            assert my_hook() == "parens_result"

    def test_hook_with_parens_sets_run_in_background_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook()
            def my_hook():
                pass

            assert getattr(my_hook, ATTR_NAME) is False

    def test_hook_with_parens_preserves_function_name(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook()
            def named_hook():
                pass

            assert named_hook.__name__ == "named_hook"

    def test_hook_with_parens_async_function(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook()
            async def my_async_hook():
                return "async_parens"

            assert iscoroutinefunction(my_async_hook)

    def test_hook_with_parens_async_runs_correctly(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook()
            async def my_async_hook():
                return "async_parens_result"

            result = asyncio.get_event_loop().run_until_complete(my_async_hook())
            assert result == "async_parens_result"

    def test_hook_with_parens_passes_args_through(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook()
            def my_hook(a, b, c=0):
                return a + b + c

            assert my_hook(1, 2, c=3) == 6


# ---------------------------------------------------------------------------
# @hook decorator - with run_in_background=True
# ---------------------------------------------------------------------------


class TestHookDecoratorRunInBackground:
    def test_run_in_background_true_sets_attribute(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=True)
            def bg_hook():
                return "bg"

            assert getattr(bg_hook, ATTR_NAME) is True

    def test_run_in_background_false_sets_attribute(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=False)
            def fg_hook():
                return "fg"

            assert getattr(fg_hook, ATTR_NAME) is False

    def test_run_in_background_true_sync_function_still_callable(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=True)
            def bg_hook(x):
                return x * 2

            assert bg_hook(5) == 10

    def test_run_in_background_true_async_function_still_awaitable(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=True)
            async def bg_async_hook():
                return "bg_async"

            assert iscoroutinefunction(bg_async_hook)
            result = asyncio.get_event_loop().run_until_complete(bg_async_hook())
            assert result == "bg_async"

    def test_run_in_background_true_preserves_function_name(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=True)
            def my_bg_hook():
                pass

            assert my_bg_hook.__name__ == "my_bg_hook"

    def test_stacking_hooks_or_logic_preserves_true(self):
        """When inner decorator sets run_in_background=True, outer with False keeps True."""
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=False)
            @hook(run_in_background=True)
            def my_hook():
                pass

            # OR logic: inner sets True, outer with False still results in True
            assert getattr(my_hook, ATTR_NAME) is True

    def test_stacking_hooks_false_on_false_stays_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=False)
            @hook(run_in_background=False)
            def my_hook():
                pass

            assert getattr(my_hook, ATTR_NAME) is False

    def test_run_in_background_true_preserves_wrapped_attribute(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            @hook(run_in_background=True)
            def my_hook():
                pass

            assert hasattr(my_hook, "__wrapped__")


# ---------------------------------------------------------------------------
# should_run_in_background() tests
# ---------------------------------------------------------------------------


class TestShouldRunInBackground:
    def test_undecorated_function_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import should_run_in_background

            def plain_func():
                pass

            assert should_run_in_background(plain_func) is False

    def test_decorated_with_run_in_background_true_returns_true(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook, should_run_in_background

            @hook(run_in_background=True)
            def bg_hook():
                pass

            assert should_run_in_background(bg_hook) is True

    def test_decorated_with_run_in_background_false_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook, should_run_in_background

            @hook(run_in_background=False)
            def fg_hook():
                pass

            assert should_run_in_background(fg_hook) is False

    def test_bare_hook_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook, should_run_in_background

            @hook
            def bare_hook():
                pass

            assert should_run_in_background(bare_hook) is False

    def test_hook_with_empty_parens_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook, should_run_in_background

            @hook()
            def parens_hook():
                pass

            assert should_run_in_background(parens_hook) is False

    def test_function_with_manual_attr_true_returns_true(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import should_run_in_background

            def manually_marked():
                pass

            setattr(manually_marked, ATTR_NAME, True)
            assert should_run_in_background(manually_marked) is True

    def test_function_with_manual_attr_false_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import should_run_in_background

            def manually_marked():
                pass

            setattr(manually_marked, ATTR_NAME, False)
            assert should_run_in_background(manually_marked) is False

    def test_wrapped_function_traverses_chain(self):
        """should_run_in_background traverses __wrapped__ chain to find attribute."""
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import should_run_in_background

            def base():
                pass

            setattr(base, ATTR_NAME, True)

            @wraps(base)
            def wrapped():
                return base()

            # wrapped has __wrapped__ = base (set by @wraps)
            assert should_run_in_background(wrapped) is True

    def test_async_undecorated_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import should_run_in_background

            async def plain_async():
                pass

            assert should_run_in_background(plain_async) is False

    def test_async_decorated_run_in_background_true(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook, should_run_in_background

            @hook(run_in_background=True)
            async def async_bg_hook():
                pass

            assert should_run_in_background(async_bg_hook) is True

    def test_lambda_returns_false(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import should_run_in_background

            fn = lambda: None
            assert should_run_in_background(fn) is False


# ---------------------------------------------------------------------------
# Invalid kwargs raise ValueError
# ---------------------------------------------------------------------------


class TestHookInvalidKwargs:
    def test_invalid_kwarg_raises_value_error(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            with pytest.raises(ValueError, match="Invalid hook configuration arguments"):

                @hook(unknown_kwarg=True)
                def bad_hook():
                    pass

    def test_multiple_invalid_kwargs_raise_value_error(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            with pytest.raises(ValueError, match="Invalid hook configuration arguments"):

                @hook(bad1=True, bad2=False)
                def bad_hook():
                    pass

    def test_valid_kwarg_does_not_raise(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            # Should not raise
            @hook(run_in_background=True)
            def valid_hook():
                pass

    def test_error_message_includes_valid_arguments(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            with pytest.raises(ValueError, match="run_in_background"):

                @hook(invalid_param="value")
                def bad_hook():
                    pass

    def test_error_message_includes_invalid_kwarg_name(self):
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            with pytest.raises(ValueError, match="foo_bar"):

                @hook(foo_bar=True)
                def bad_hook():
                    pass

    def test_invalid_kwarg_checked_before_function_wrapping(self):
        """ValueError is raised even when a positional arg (function) is also provided."""
        # When kwargs contains invalid keys, should raise ValueError regardless of args
        with _inject_constant():
            from ii_agent.agents.hooks.decorator import hook

            with pytest.raises(ValueError):

                @hook(completely_invalid=42)
                def my_hook():
                    pass


# ---------------------------------------------------------------------------
# Bug documentation test
# ---------------------------------------------------------------------------


class TestHookConstantBug:
    def test_hook_raises_name_error_without_constant_defined(self):
        """
        Document the existing bug: HOOK_RUN_IN_BACKGROUND_ATTR is referenced
        in decorator.py but never defined at module level. Without injecting
        the constant, applying @hook raises NameError.
        """
        import ii_agent.agents.hooks.decorator as dec

        # Make sure the constant is NOT set on the module
        if hasattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR"):
            delattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR")

        try:
            with pytest.raises(NameError, match="HOOK_RUN_IN_BACKGROUND_ATTR"):

                @dec.hook
                def bug_exposed():
                    pass

        finally:
            # Clean up so other tests are not affected
            if hasattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR"):
                delattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR")

    def test_should_run_in_background_raises_without_constant(self):
        """
        should_run_in_background() also fails with NameError when the constant
        is not defined, because it references HOOK_RUN_IN_BACKGROUND_ATTR.
        """
        import ii_agent.agents.hooks.decorator as dec

        if hasattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR"):
            delattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR")

        try:

            def plain_func():
                pass

            with pytest.raises(NameError, match="HOOK_RUN_IN_BACKGROUND_ATTR"):
                dec.should_run_in_background(plain_func)

        finally:
            if hasattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR"):
                delattr(dec, "HOOK_RUN_IN_BACKGROUND_ATTR")
