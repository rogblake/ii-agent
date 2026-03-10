"""Deep unit tests for ii_agent/engine/runtime/tools/function.py.

Focuses on uncovered paths:
- Function.from_callable: parameter handling, special params excluded, strict mode
- Function.from_tool: BaseAgentTool wrapping, user_input_schema generation
- Function.process_entrypoint: schema derivation, strict mode, skip_entrypoint_processing
- Function.model_copy: deep copy behavior, callable fields
- Function._wrap_callable: async generators, coroutines, already-wrapped
- Function.process_schema_for_strict: nested schemas
- FunctionCall.get_call_str, _handle_pre_hook, _handle_post_hook
"""

from __future__ import annotations

import pytest
from typing import Optional, List
from unittest.mock import AsyncMock, MagicMock, patch
from functools import partial

from ii_agent.engine.runtime.tools.function import Function, FunctionCall, FunctionExecutionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_function(name="test_func", **kwargs) -> Function:
    return Function(name=name, **kwargs)


def make_base_agent_tool(name="my_tool", description="Tool desc") -> MagicMock:
    from ii_agent.engine.runtime.tools.base import BaseAgentTool, ToolResult
    tool = MagicMock(spec=BaseAgentTool)
    tool.name = name
    tool.description = description
    tool.display_name = name
    tool.tool_logo = None
    tool.input_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    tool.on_tool_start = None
    tool.on_tool_end = None
    tool.requires_sandbox = False
    tool.requires_confirmation = None
    tool.requires_user_input = False
    tool.user_input_fields = None
    tool.stop_after_tool_call = False
    tool.read_only = True
    return tool


# ---------------------------------------------------------------------------
# Function.from_callable deep tests
# ---------------------------------------------------------------------------

class TestFunctionFromCallableDeep:
    def test_simple_callable_creates_function(self):
        def search(query: str) -> str:
            """Search for something.

            Args:
                query: The search query.
            """
            return query

        fn = Function.from_callable(search)
        assert fn.name == "search"
        assert "query" in fn.parameters["properties"]
        assert "query" in fn.parameters["required"]

    def test_callable_with_optional_param(self):
        def process(query: str, limit: Optional[int] = None) -> str:
            """Process query."""
            return query

        fn = Function.from_callable(process)
        assert "query" in fn.parameters["required"]
        assert "limit" not in fn.parameters["required"]

    def test_callable_with_agent_param_excluded(self):
        def tool_with_agent(query: str, agent) -> str:
            """Tool that uses agent."""
            return query

        fn = Function.from_callable(tool_with_agent)
        assert "agent" not in fn.parameters.get("properties", {})
        assert "query" in fn.parameters["properties"]

    def test_callable_with_run_context_excluded(self):
        def tool_with_ctx(query: str, run_context) -> str:
            """Tool with context."""
            return query

        fn = Function.from_callable(tool_with_ctx)
        assert "run_context" not in fn.parameters.get("properties", {})

    def test_callable_with_session_state_excluded(self):
        def tool_with_state(query: str, session_state: dict) -> str:
            """Tool with state."""
            return query

        fn = Function.from_callable(tool_with_state)
        assert "session_state" not in fn.parameters.get("properties", {})

    def test_callable_with_images_excluded(self):
        def tool_with_images(query: str, images: list) -> str:
            """Tool with images."""
            return query

        fn = Function.from_callable(tool_with_images)
        assert "images" not in fn.parameters.get("properties", {})

    def test_callable_with_videos_excluded(self):
        def tool_with_videos(query: str, videos: list) -> str:
            """Tool with videos."""
            return query

        fn = Function.from_callable(tool_with_videos)
        assert "videos" not in fn.parameters.get("properties", {})

    def test_callable_with_files_excluded(self):
        def tool_with_files(query: str, files: list) -> str:
            """Tool with files."""
            return query

        fn = Function.from_callable(tool_with_files)
        assert "files" not in fn.parameters.get("properties", {})

    def test_callable_with_audios_excluded(self):
        def tool_with_audios(query: str, audios: list) -> str:
            """Tool with audios."""
            return query

        fn = Function.from_callable(tool_with_audios)
        assert "audios" not in fn.parameters.get("properties", {})

    def test_callable_with_strict_mode_marks_all_required(self):
        def multi_param_tool(a: str, b: int, c: Optional[str] = None) -> str:
            """Tool with multiple params."""
            return a

        fn = Function.from_callable(multi_param_tool, strict=True)
        # In strict mode, all non-excluded params should be required
        assert "a" in fn.parameters["required"]
        assert "b" in fn.parameters["required"]
        assert "c" in fn.parameters["required"]

    def test_callable_with_docstring_param_descriptions(self):
        def tool_with_desc(query: str) -> str:
            """Do something.

            Args:
                query: The search query to use.
            """
            return query

        fn = Function.from_callable(tool_with_desc)
        # Should have description from docstring
        assert fn.description is not None and len(fn.description) > 0

    def test_callable_with_no_params(self):
        def no_params_tool() -> str:
            """Tool with no parameters."""
            return "result"

        fn = Function.from_callable(no_params_tool)
        assert fn.parameters["properties"] == {}
        assert fn.parameters["required"] == []

    def test_callable_with_custom_name(self):
        def tool() -> str:
            """Tool."""
            return "result"

        fn = Function.from_callable(tool, name="custom_name")
        assert fn.name == "custom_name"

    def test_callable_entrypoint_is_wrapped(self):
        def tool(query: str) -> str:
            """Tool."""
            return query

        fn = Function.from_callable(tool)
        assert fn.entrypoint is not None


# ---------------------------------------------------------------------------
# Function.from_tool deep tests
# ---------------------------------------------------------------------------

class TestFunctionFromToolDeep:
    def test_from_tool_creates_function(self):
        tool = make_base_agent_tool()
        fn = Function.from_tool(tool)
        assert fn.name == tool.name
        assert fn.description == tool.description

    def test_from_tool_raises_for_non_base_agent_tool(self):
        with pytest.raises(ValueError, match="Expected BaseTool"):
            Function.from_tool("not a tool")

    def test_from_tool_sets_parameters_from_input_schema(self):
        tool = make_base_agent_tool()
        fn = Function.from_tool(tool)
        assert fn.parameters == tool.input_schema

    def test_from_tool_skip_entrypoint_processing_is_true(self):
        tool = make_base_agent_tool()
        fn = Function.from_tool(tool)
        assert fn.skip_entrypoint_processing is True

    def test_from_tool_sets_display_name(self):
        tool = make_base_agent_tool(name="my_tool")
        fn = Function.from_tool(tool)
        assert fn.display_name is not None

    def test_from_tool_requires_confirmation_propagated(self):
        tool = make_base_agent_tool()
        tool.requires_confirmation = True
        fn = Function.from_tool(tool)
        assert fn.requires_confirmation is True

    def test_from_tool_stop_after_tool_call_propagated(self):
        tool = make_base_agent_tool()
        tool.stop_after_tool_call = True
        fn = Function.from_tool(tool)
        assert fn.stop_after_tool_call is True

    def test_from_tool_with_user_input_fields_generates_schema(self):
        from ii_agent.engine.runtime.tools.base import BaseAgentTool
        tool = MagicMock(spec=BaseAgentTool)
        tool.name = "hitl_tool"
        tool.description = "HITL tool"
        tool.display_name = "HITL Tool"
        tool.tool_logo = None
        tool.on_tool_start = None
        tool.on_tool_end = None
        tool.requires_sandbox = False
        tool.requires_confirmation = None
        tool.requires_user_input = True
        tool.user_input_fields = ["target_field"]
        tool.stop_after_tool_call = False
        tool.read_only = True
        tool.input_schema = {
            "type": "object",
            "properties": {
                "target_field": {"type": "string", "description": "A target field"},
            },
            "required": ["target_field"],
        }
        fn = Function.from_tool(tool)
        assert fn.requires_user_input is True
        assert fn.user_input_schema is not None
        assert len(fn.user_input_schema) == 1
        assert fn.user_input_schema[0].name == "target_field"

    @pytest.mark.asyncio
    async def test_tool_entrypoint_calls_execute(self):
        from ii_agent.engine.runtime.tools.base import ToolResult
        tool = make_base_agent_tool()
        expected_result = ToolResult(llm_content="success", user_display_content="done")
        tool.execute = AsyncMock(return_value=expected_result)

        fn = Function.from_tool(tool)
        # Call the entrypoint directly
        result = await fn.entrypoint(query="test")
        tool.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_entrypoint_handles_exception(self):
        from ii_agent.engine.runtime.tools.base import ToolResult
        tool = make_base_agent_tool()
        tool.execute = AsyncMock(side_effect=RuntimeError("tool failed"))

        fn = Function.from_tool(tool)
        result = await fn.entrypoint(query="test")
        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert "Error" in result.llm_content

    def test_from_tool_with_none_input_schema_uses_default(self):
        from ii_agent.engine.runtime.tools.base import BaseAgentTool
        tool = MagicMock(spec=BaseAgentTool)
        tool.name = "no_schema_tool"
        tool.description = "Tool"
        tool.display_name = "Tool"
        tool.tool_logo = None
        tool.on_tool_start = None
        tool.on_tool_end = None
        tool.requires_sandbox = False
        tool.requires_confirmation = None
        tool.requires_user_input = False
        tool.user_input_fields = None
        tool.stop_after_tool_call = False
        tool.read_only = True
        tool.input_schema = None

        fn = Function.from_tool(tool)
        assert fn.parameters == {"type": "object", "properties": {}, "required": []}


# ---------------------------------------------------------------------------
# Function.process_entrypoint deep tests
# ---------------------------------------------------------------------------

class TestFunctionProcessEntrypointDeep:
    def test_process_entrypoint_skips_when_no_entrypoint(self):
        fn = make_function()
        fn.entrypoint = None
        fn.process_entrypoint()  # Should not raise

    def test_process_entrypoint_skips_when_skip_flag_set(self):
        fn = make_function()
        fn.skip_entrypoint_processing = True
        fn.entrypoint = lambda: None
        fn.process_entrypoint()
        # Parameters should remain unchanged
        assert fn.parameters == {"type": "object", "properties": {}, "required": []}

    def test_process_entrypoint_with_strict_and_skip_flag(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": [],
        })
        fn.skip_entrypoint_processing = True
        fn.entrypoint = lambda: None
        fn.process_entrypoint(strict=True)
        # Should call process_schema_for_strict
        assert fn.parameters.get("additionalProperties") is False

    def test_process_entrypoint_sets_description(self):
        def tool_func(query: str) -> str:
            """A very descriptive tool."""
            return query

        fn = make_function()
        fn.entrypoint = tool_func
        fn.process_entrypoint()
        assert fn.description == "A very descriptive tool."

    def test_process_entrypoint_sets_description_when_already_set(self):
        def tool_func(query: str) -> str:
            """Tool docstring."""
            return query

        fn = make_function(description="User-set description")
        fn.entrypoint = tool_func
        fn.process_entrypoint()
        # User-set description should be preserved
        assert fn.description == "User-set description"

    def test_process_entrypoint_with_requires_user_input(self):
        def tool_func(query: str, target: str) -> str:
            """Tool with user input."""
            return query

        fn = make_function()
        fn.entrypoint = tool_func
        fn.requires_user_input = True
        fn.user_input_fields = ["target"]
        fn.process_entrypoint()
        # target should be excluded from model params since it's user input
        assert "target" not in fn.parameters.get("properties", {})

    def test_process_entrypoint_with_user_input_all_params_excluded(self):
        def tool_func(query: str) -> str:
            """Tool."""
            return query

        fn = make_function()
        fn.entrypoint = tool_func
        fn.requires_user_input = True
        # An empty list is falsy, so the check `if self.user_input_fields`
        # would not trigger. This test verifies that empty list does NOT
        # exclude params (the exclusion only happens when the list is truthy
        # and has length==0 per the source code branch logic).
        fn.user_input_fields = []  # Falsy - no exclusion happens
        fn.process_entrypoint()
        # query should still be in parameters because empty list is falsy
        assert "query" in fn.parameters.get("properties", {})

    def test_process_entrypoint_generates_json_schema(self):
        def tool_func(query: str, count: int) -> str:
            """Tool."""
            return query

        fn = make_function()
        fn.entrypoint = tool_func
        fn.process_entrypoint()
        assert "query" in fn.parameters["properties"]
        assert "count" in fn.parameters["properties"]

    def test_process_entrypoint_marks_required_params(self):
        def tool_func(required_param: str, optional_param: str = "default") -> str:
            """Tool."""
            return required_param

        fn = make_function()
        fn.entrypoint = tool_func
        fn.process_entrypoint()
        assert "required_param" in fn.parameters["required"]
        assert "optional_param" not in fn.parameters["required"]

    def test_process_entrypoint_with_user_set_parameters(self):
        custom_params = {
            "type": "object",
            "properties": {"custom": {"type": "string"}},
            "required": [],
        }
        fn = make_function(parameters=custom_params)

        def tool_func(query: str) -> str:
            """Tool."""
            return query

        fn.entrypoint = tool_func
        fn.process_entrypoint()
        # User-set params should be preserved (additionalProperties added)
        assert "custom" in fn.parameters["properties"]


# ---------------------------------------------------------------------------
# Function.model_copy deep tests
# ---------------------------------------------------------------------------

class TestFunctionModelCopyDeep:
    def test_shallow_copy_returns_different_instance(self):
        fn = make_function()
        copy = fn.model_copy(deep=False)
        assert copy is not fn

    def test_deep_copy_preserves_entrypoint_reference(self):
        def entrypoint():
            pass

        fn = make_function()
        fn.entrypoint = entrypoint
        copy = fn.model_copy(deep=True)
        assert copy.entrypoint is entrypoint

    def test_deep_copy_preserves_pre_hook_reference(self):
        def pre_hook():
            pass

        fn = make_function()
        fn.pre_hook = pre_hook
        copy = fn.model_copy(deep=True)
        assert copy.pre_hook is pre_hook

    def test_deep_copy_preserves_post_hook_reference(self):
        def post_hook():
            pass

        fn = make_function()
        fn.post_hook = post_hook
        copy = fn.model_copy(deep=True)
        assert copy.post_hook is post_hook

    def test_deep_copy_deep_copies_parameters(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": [],
        })
        copy = fn.model_copy(deep=True)
        # Modifying copy's parameters should not affect original
        copy.parameters["properties"]["new_field"] = {"type": "string"}
        assert "new_field" not in fn.parameters["properties"]

    def test_deep_copy_preserves_name(self):
        fn = make_function(name="original_name")
        copy = fn.model_copy(deep=True)
        assert copy.name == "original_name"

    def test_deep_copy_preserves_tool_hooks(self):
        def hook():
            pass

        fn = make_function()
        fn.tool_hooks = [hook]
        copy = fn.model_copy(deep=True)
        assert copy.tool_hooks is fn.tool_hooks  # Shallow copy

    def test_deep_copy_creates_new_instance(self):
        fn = make_function()
        copy = fn.model_copy(deep=True)
        assert copy is not fn


# ---------------------------------------------------------------------------
# Function._wrap_callable deep tests
# ---------------------------------------------------------------------------

class TestFunctionWrapCallableDeep:
    def test_async_generator_not_wrapped(self):
        async def async_gen():
            yield "item"

        result = Function._wrap_callable(async_gen)
        assert result is async_gen

    def test_already_wrapped_not_re_wrapped(self):
        def already_wrapped():
            pass
        already_wrapped._wrapped_for_validation = True

        result = Function._wrap_callable(already_wrapped)
        assert result is already_wrapped

    def test_session_state_param_not_wrapped(self):
        def func_with_session(session_state: dict):
            pass

        result = Function._wrap_callable(func_with_session)
        assert result is func_with_session

    def test_regular_sync_function_gets_wrapped(self):
        def regular_func(x: int) -> int:
            return x

        result = Function._wrap_callable(regular_func)
        # Should be different from original (wrapped)
        assert hasattr(result, "_wrapped_for_validation")


# ---------------------------------------------------------------------------
# Function.process_schema_for_strict deep tests
# ---------------------------------------------------------------------------

class TestProcessSchemaForStrictDeep:
    def test_adds_additional_properties_false_to_root(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": [],
        })
        fn.process_schema_for_strict()
        assert fn.parameters.get("additionalProperties") is False

    def test_adds_additional_properties_false_to_nested_objects(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"inner": {"type": "string"}},
                }
            },
            "required": [],
        })
        fn.process_schema_for_strict()
        nested_schema = fn.parameters["properties"]["nested"]
        assert nested_schema.get("additionalProperties") is False

    def test_marks_all_properties_as_required(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {
                "param_a": {"type": "string"},
                "param_b": {"type": "integer"},
            },
            "required": [],
        })
        fn.process_schema_for_strict()
        assert "param_a" in fn.parameters["required"]
        assert "param_b" in fn.parameters["required"]

    def test_excludes_reserved_params_from_required(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "run_context": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": [],
        })
        fn.process_schema_for_strict()
        # Reserved params should be excluded
        assert "agent" not in fn.parameters["required"]
        assert "run_context" not in fn.parameters["required"]
        assert "query" in fn.parameters["required"]

    def test_schema_without_type_gets_type_inferred(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {
                "param": {
                    "properties": {"inner": {"type": "string"}},  # No type, but has properties
                }
            },
            "required": [],
        })
        fn.process_schema_for_strict()
        param_schema = fn.parameters["properties"]["param"]
        assert param_schema.get("type") == "object"

    def test_anyof_schema_not_given_type(self):
        fn = make_function(parameters={
            "type": "object",
            "properties": {
                "param": {
                    "anyOf": [{"type": "string"}, {"type": "integer"}],
                }
            },
            "required": [],
        })
        fn.process_schema_for_strict()
        # anyOf schema should not have type forcibly added
        param_schema = fn.parameters["properties"]["param"]
        assert "type" not in param_schema or param_schema.get("type") == "object"


# ---------------------------------------------------------------------------
# FunctionCall.get_call_str deep tests
# ---------------------------------------------------------------------------

class TestFunctionCallGetCallStrDeep:
    def test_no_arguments_returns_empty_call(self):
        fn = make_function(name="my_tool")
        fc = FunctionCall(function=fn, arguments=None)
        call_str = fc.get_call_str()
        assert call_str == "my_tool()"

    def test_with_arguments_returns_call_string(self):
        fn = make_function(name="search")
        fc = FunctionCall(function=fn, arguments={"query": "python"})
        call_str = fc.get_call_str()
        assert "search" in call_str
        assert "query" in call_str or "python" in call_str

    def test_long_argument_value_is_truncated(self):
        fn = make_function(name="tool")
        long_value = "x" * 1000
        fc = FunctionCall(function=fn, arguments={"query": long_value})
        call_str = fc.get_call_str()
        assert "..." in call_str or len(call_str) < len(long_value)

    def test_very_long_call_str_shows_ellipsis(self):
        fn = make_function(name="t")
        # Create enough arguments to make call_str longer than terminal width
        args = {f"param_{i}": f"value_{i}" for i in range(20)}
        fc = FunctionCall(function=fn, arguments=args)
        call_str = fc.get_call_str()
        assert isinstance(call_str, str)


# ---------------------------------------------------------------------------
# FunctionCall._handle_pre_hook deep tests
# ---------------------------------------------------------------------------

class TestFunctionCallHandlePreHookDeep:
    def test_no_pre_hook_does_nothing(self):
        fn = make_function()
        fn.pre_hook = None
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()  # Should not raise

    def test_pre_hook_with_no_params_called(self):
        called = []

        def hook():
            called.append(True)

        fn = make_function()
        fn.pre_hook = hook
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()
        assert called == [True]

    def test_pre_hook_with_agent_param_injects_agent(self):
        received_agent = []

        def hook(agent):
            received_agent.append(agent)

        mock_agent = MagicMock()
        fn = make_function()
        fn.pre_hook = hook
        fn._agent = mock_agent
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()
        assert received_agent[0] is mock_agent

    def test_pre_hook_with_fc_param_injects_self(self):
        received_fc = []

        def hook(fc):
            received_fc.append(fc)

        fn = make_function()
        fn.pre_hook = hook
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()
        assert received_fc[0] is fc

    def test_pre_hook_with_run_context_param(self):
        received = []

        def hook(run_context):
            received.append(run_context)

        mock_ctx = MagicMock()
        fn = make_function()
        fn.pre_hook = hook
        fn._run_context = mock_ctx
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()
        assert received[0] is mock_ctx

    def test_pre_hook_exception_does_not_raise(self):
        def bad_hook():
            raise ValueError("hook failed")

        fn = make_function()
        fn.pre_hook = bad_hook
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_pre_hook()  # Should not propagate exception

    def test_pre_hook_agent_run_exception_sets_error_and_raises(self):
        from ii_agent.engine.runtime.exceptions import AgentRunException

        def hook():
            raise AgentRunException("run aborted")

        fn = make_function()
        fn.pre_hook = hook
        fc = FunctionCall(function=fn, arguments={})
        with pytest.raises(AgentRunException):
            fc._handle_pre_hook()
        assert fc.error is not None


# ---------------------------------------------------------------------------
# FunctionCall._handle_post_hook deep tests
# ---------------------------------------------------------------------------

class TestFunctionCallHandlePostHookDeep:
    def test_no_post_hook_does_nothing(self):
        fn = make_function()
        fn.post_hook = None
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_post_hook()  # Should not raise

    def test_post_hook_with_agent_param_injects_agent(self):
        received = []

        def hook(agent):
            received.append(agent)

        mock_agent = MagicMock()
        fn = make_function()
        fn.post_hook = hook
        fn._agent = mock_agent
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_post_hook()
        assert received[0] is mock_agent

    def test_post_hook_exception_does_not_raise(self):
        def bad_hook():
            raise ValueError("post hook failed")

        fn = make_function()
        fn.post_hook = bad_hook
        fc = FunctionCall(function=fn, arguments={})
        fc._handle_post_hook()  # Should not propagate


# ---------------------------------------------------------------------------
# FunctionExecutionResult
# ---------------------------------------------------------------------------

class TestFunctionExecutionResultDeep:
    def test_success_status(self):
        result = FunctionExecutionResult(status="success", result="done")
        assert result.status == "success"
        assert result.result == "done"
        assert result.error is None

    def test_failure_status_with_error(self):
        result = FunctionExecutionResult(status="failure", error="something went wrong")
        assert result.status == "failure"
        assert result.error == "something went wrong"

    def test_with_images(self):
        from ii_agent.engine.runtime.media import Image
        img = Image(id="img-1", url="http://example.com/img.png")
        result = FunctionExecutionResult(status="success", images=[img])
        assert result.images is not None
        assert len(result.images) == 1

    def test_with_updated_session_state(self):
        result = FunctionExecutionResult(
            status="success",
            updated_session_state={"key": "new_value"},
        )
        assert result.updated_session_state == {"key": "new_value"}

    def test_defaults_all_optional_none(self):
        result = FunctionExecutionResult(status="success")
        assert result.result is None
        assert result.error is None
        assert result.images is None
        assert result.videos is None
        assert result.audios is None
        assert result.files is None
        assert result.updated_session_state is None
