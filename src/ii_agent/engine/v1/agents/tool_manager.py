from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Union,
    cast,
)

from ii_agent.core.logger import logger
from ii_agent.engine.v1.models.base import Model
from ii_agent.engine.v1.models.response import ModelResponse, ModelResponseEvent, ToolExecution
from ii_agent.engine.v1.run.agent import RunEvent, RunOutput, RunOutputEvent
from ii_agent.engine.v1.run.events import (
    create_tool_call_completed_event,
    create_tool_call_started_event,
    handle_event,
)
from ii_agent.engine.v1.run.messages import RunMessages
from ii_agent.engine.v1.tools import Toolkit
from ii_agent.engine.v1.tools.base import BaseAgentTool
from ii_agent.engine.v1.tools.function import Function
from ii_agent.engine.v1.models.message import Message
from ii_agent.engine.v1.utils.agent import (
    collect_joint_audios,
    collect_joint_files,
    collect_joint_images,
    collect_joint_videos,
)

if TYPE_CHECKING:
    from ii_agent.engine.v1.run import RunContext
    from ii_agent.engine.v1.agent_sessions import AgentSession


class ToolManager:
    """Manages tool lifecycle, connection, and model preparation."""

    def __init__(self, model: Model):
        self._model = model
        self._mcp_tools_initialized: List[Any] = []
        self._connectable_tools_initialized: List[Any] = []
        self.tool_instructions: List[str] = []

    async def _connect_mcp_tools(self, tools: Optional[List]) -> None:
        """Connect the MCP tools."""
        if tools:
            for tool in tools:
                if (
                    hasattr(type(tool), "__mro__")
                    and any(c.__name__ in ["MCPTools", "MultiMCPTools"] for c in type(tool).__mro__)
                    and not tool.initialized
                ):
                    try:
                        await tool.connect()
                        self._mcp_tools_initialized.append(tool)
                    except Exception as e:
                        logger.warning(f"Error connecting tool: {str(e)}")

    async def disconnect_mcp_tools(self) -> None:
        """Disconnect the MCP tools."""
        for tool in self._mcp_tools_initialized:
            try:
                await tool.close()
            except Exception as e:
                logger.warning(f"Error disconnecting tool: {str(e)}")
        self._mcp_tools_initialized = []

    def _connect_connectable_tools(self, tools: Optional[List]) -> None:
        """Connect tools that require connection management."""
        if tools:
            for tool in tools:
                if (
                    hasattr(tool, "requires_connect")
                    and tool.requires_connect
                    and hasattr(tool, "connect")
                    and tool not in self._connectable_tools_initialized
                ):
                    try:
                        tool.connect()
                        self._connectable_tools_initialized.append(tool)
                    except Exception as e:
                        logger.warning(f"Error connecting tool: {str(e)}")

    def disconnect_connectable_tools(self) -> None:
        """Disconnect tools that require connection management."""
        for tool in self._connectable_tools_initialized:
            if hasattr(tool, "close"):
                try:
                    tool.close()
                except Exception as e:
                    logger.warning(f"Error disconnecting tool: {str(e)}")
        self._connectable_tools_initialized = []

    async def disconnect_all(self) -> None:
        """Disconnect all tools (connectable + MCP)."""
        self.disconnect_connectable_tools()
        await self.disconnect_mcp_tools()

    async def connect_and_get_tools(
        self,
        tools: Optional[List],
        check_mcp_tools: bool = True,
    ) -> List[Union[Toolkit, Callable, Function, Dict]]:
        """Connect tools and return processed list."""
        agent_tools: List[Union[Toolkit, Callable, Function, Dict]] = []

        self._connect_connectable_tools(tools)
        await self._connect_mcp_tools(tools)

        if tools is not None:
            for tool in tools:
                is_mcp_tool = hasattr(type(tool), "__mro__") and any(
                    c.__name__ in ["MCPTools", "MultiMCPTools"] for c in type(tool).__mro__
                )

                if is_mcp_tool:
                    if tool.refresh_connection:
                        try:
                            is_alive = await tool.is_alive()
                            if not is_alive:
                                await tool.connect(force=True)
                        except (RuntimeError, BaseException) as e:
                            logger.warning(
                                f"Failed to check if MCP tool is alive or to connect to it: {e}"
                            )
                            continue

                        try:
                            await tool.build_tools()
                        except (RuntimeError, BaseException) as e:
                            logger.warning(f"Failed to build tools for {str(tool)}: {e}")
                            continue

                    if check_mcp_tools and not tool.initialized:
                        continue

                agent_tools.append(tool)

        return agent_tools

    async def run_tool(
        self,
        run_response: RunOutput,
        run_messages: RunMessages,
        tool: ToolExecution,
        functions: Optional[Dict[str, Function]] = None,
        stream_events: bool = False,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
    ) -> AsyncIterator[RunOutputEvent]:
        """Execute a single tool call."""
        function_call = self._model.get_function_call_to_run_from_tool_execution(tool, functions)
        function_call_results: List[Message] = []

        async for call_result in self._model.arun_function_calls(
            function_calls=[function_call],
            function_call_results=function_call_results,
            skip_pause_check=True,
        ):
            if isinstance(call_result, ModelResponse):
                if call_result.event == ModelResponseEvent.tool_call_started.value:
                    if stream_events:
                        yield handle_event(
                            create_tool_call_started_event(
                                from_run_response=run_response, tool=tool
                            ),
                            run_response,
                            events_to_skip=events_to_skip,
                            store_events=store_events,
                        )
                if (
                    call_result.event == ModelResponseEvent.tool_call_completed.value
                    and call_result.tool_executions
                ):
                    tool_execution = call_result.tool_executions[0]
                    tool.result = tool_execution.result
                    tool.tool_call_error = tool_execution.tool_call_error
                    if stream_events:
                        yield handle_event(
                            create_tool_call_completed_event(
                                from_run_response=run_response,
                                tool=tool,
                                content=call_result.content,
                            ),
                            run_response,
                            events_to_skip=events_to_skip,
                            store_events=store_events,
                        )
        if len(function_call_results) > 0:
            run_messages.messages.extend(function_call_results)

    def determine_tools_for_model(
        self,
        processed_tools: List[Union[Toolkit, Callable, Function, Dict]],
        tool_hooks: Optional[List[Callable]],
        run_response: RunOutput,
        run_context: RunContext,
        session: AgentSession,
        stream: bool = False,
        stream_events: bool = False,
        user_id: Optional[str] = None,
        agent_ref: Any = None,
        delegate_func: Optional[Function] = None,
    ) -> List[Union[Function, dict]]:
        """Process tools into Functions for the model.

        Args:
            processed_tools: Raw tool list from connect_and_get_tools.
            tool_hooks: Tool middleware hooks.
            run_response: Current run response.
            run_context: Current run context.
            session: Current agent session.
            stream: Whether streaming.
            stream_events: Whether streaming events.
            user_id: Current user ID.
            agent_ref: Reference to the agent (set on Function._agent for tool callbacks).
            delegate_func: Optional delegation function from DelegationManager.
        """
        _function_names = []
        _functions: List[Union[Function, dict]] = []
        self.tool_instructions = []

        if processed_tools is not None and len(processed_tools) > 0:
            logger.debug(f"[V1 Agent] Processing {len(processed_tools)} tools for model")

            for tool in processed_tools:
                if isinstance(tool, Dict):
                    _functions.append(tool)
                    logger.debug(f"Included builtin tool {tool}")
                elif isinstance(tool, BaseAgentTool):
                    if tool.name in _function_names:
                        continue
                    _function_names.append(tool.name)
                    _func = Function.from_tool(tool)
                    _func.process_entrypoint()
                    _func = _func.model_copy(deep=True)
                    _func._agent = agent_ref
                    if tool_hooks is not None:
                        _func.tool_hooks = tool_hooks
                    _functions.append(_func)
                    logger.debug(f"Added tool {tool.name} from BaseAgentTool")
                    if tool.add_instructions and tool.instructions is not None:
                        self.tool_instructions.append(tool.instructions)

                elif isinstance(tool, Toolkit):
                    for name, _func in tool.functions.items():
                        if name in _function_names:
                            continue
                        _function_names.append(name)
                        _func = _func.model_copy(deep=True)
                        _func._agent = agent_ref
                        _func.process_entrypoint()
                        if tool_hooks is not None:
                            _func.tool_hooks = tool_hooks
                        _functions.append(_func)
                        logger.debug(f"Added tool {name} from {tool.name}")
                    if tool.add_instructions and tool.instructions is not None:
                        self.tool_instructions.append(tool.instructions)

                elif isinstance(tool, Function):
                    if tool.name in _function_names:
                        continue
                    _function_names.append(tool.name)
                    tool.process_entrypoint()
                    _tool = tool.model_copy(deep=True)
                    _tool._agent = agent_ref
                    if tool_hooks is not None:
                        tool.tool_hooks = tool_hooks
                    _functions.append(_tool)
                    logger.debug(f"Added tool {tool.name}")
                    if tool.add_instructions and tool.instructions is not None:
                        self.tool_instructions.append(tool.instructions)

                elif callable(tool):
                    try:
                        function_name = tool.__name__
                        if function_name in _function_names:
                            continue
                        _function_names.append(function_name)
                        _func = Function.from_callable(tool)
                        _func = _func.model_copy(deep=True)
                        _func._agent = agent_ref
                        if tool_hooks is not None:
                            _func.tool_hooks = tool_hooks
                        _functions.append(_func)
                        logger.debug(f"Added tool {_func.name}")
                    except Exception as e:
                        logger.warning(f"Could not add tool {tool}: {e}")

        # Update the session state for the functions
        if _functions:
            from inspect import signature

            needs_media = any(
                any(
                    param in signature(func.entrypoint).parameters
                    for param in ["images", "videos", "audios", "files"]
                )
                for func in _functions
                if isinstance(func, Function) and func.entrypoint is not None
            )

            joint_images = (
                collect_joint_images(run_response.input, session) if needs_media else None
            )
            joint_files = collect_joint_files(run_response.input) if needs_media else None
            joint_audios = (
                collect_joint_audios(run_response.input, session) if needs_media else None
            )
            joint_videos = (
                collect_joint_videos(run_response.input, session) if needs_media else None
            )

            for func in _functions:
                if isinstance(func, Function):
                    func._run_context = run_context
                    func._images = joint_images
                    func._files = joint_files
                    func._audios = joint_audios
                    func._videos = joint_videos

        # Add delegation tool for sub-agents
        if delegate_func is not None:
            delegate_func._agent = agent_ref
            delegate_func._run_context = run_context
            _functions.append(delegate_func)
            logger.debug("Added delegation tool for sub-agents")

        logger.debug(f"[V1 Agent] Converted {len(_functions)} tools to Functions for LLM")
        logger.debug(f"[V1 Agent] Function names: {[f.name if isinstance(f, Function) else str(f.get('name', 'unknown')) for f in _functions]}")

        return _functions
