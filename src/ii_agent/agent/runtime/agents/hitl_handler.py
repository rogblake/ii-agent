from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Union,
    cast,
)

from ii_agent.core.logger import logger
from ii_agent.agent.runtime.models.base import Model
from ii_agent.agent.runtime.models.message import Message
from ii_agent.agent.runtime.models.metrics import Metrics
from ii_agent.agent.runtime.models.response import ToolExecution
from ii_agent.agent.runtime.run import RunContext, RunStatus
from ii_agent.agent.runtime.run.agent import RunEvent, RunOutput, RunOutputEvent
from ii_agent.agent.runtime.run.events import (
    create_run_paused_event,
    create_tool_call_completed_event,
    handle_event,
)
from ii_agent.agent.runtime.run.messages import RunMessages
from ii_agent.agent.runtime.tools.function import Function
from ii_agent.agent.runtime.utils.response import get_paused_content

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agent_sessions import AgentSession
    from ii_agent.agent.runtime.agents.tool_manager import ToolManager


# Type for the cleanup callback (avoids HITLHandler depending on RunMixin)
CleanupFn = Callable[..., Awaitable[None]]


class HITLHandler:
    """Handles Human-in-the-Loop (HITL) pause/resume flows."""

    def __init__(self, model: Model, tool_manager: ToolManager):
        self._model = model
        self._tool_manager = tool_manager

    async def handle_paused(
        self,
        run_response: RunOutput,
        session: AgentSession,
        run_context: Optional[RunContext],
        cleanup_fn: CleanupFn,
    ) -> RunOutput:
        """Handle a paused agent run (non-streaming)."""
        run_response.status = RunStatus.PAUSED
        if not run_response.content:
            run_response.content = get_paused_content(run_response)

        await cleanup_fn(
            run_response=run_response, session=session, run_context=run_context
        )

        logger.debug(f"Agent Run Paused: {run_response.run_id}", center=True, symbol="*")
        return run_response

    async def handle_paused_stream(
        self,
        run_response: RunOutput,
        session: AgentSession,
        run_context: Optional[RunContext],
        cleanup_fn: CleanupFn,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
    ) -> AsyncIterator[RunOutputEvent]:
        """Handle a paused agent run (streaming variant)."""
        run_response.status = RunStatus.PAUSED
        if not run_response.content:
            run_response.content = get_paused_content(run_response)

        pause_event = handle_event(
            create_run_paused_event(
                from_run_response=run_response,
                tools=run_response.tools,
                requirements=run_response.requirements,
            ),
            run_response,
            events_to_skip=events_to_skip,
            store_events=store_events,
        )

        await cleanup_fn(
            run_response=run_response, session=session, run_context=run_context
        )

        yield pause_event

        logger.debug(f"Agent Run Paused: {run_response.run_id}", center=True, symbol="*")

    def _handle_external_execution_update(self, run_messages: RunMessages, tool: ToolExecution):
        """Handle tool update for external execution."""
        if tool.result is not None:
            for msg in run_messages.messages:
                if msg.tool_call_id == tool.tool_call_id:
                    break
            else:
                run_messages.messages.append(
                    Message(
                        role=self._model.tool_message_role,
                        content=tool.result,
                        tool_call_id=tool.tool_call_id,
                        tool_name=tool.tool_name,
                        tool_args=tool.tool_args,
                        tool_call_error=tool.tool_call_error,
                        stop_after_tool_call=tool.stop_after_tool_call,
                    )
                )
            tool.external_execution_required = False
        else:
            raise ValueError(
                f"Tool {tool.tool_name} requires external execution, cannot continue run"
            )

    def _handle_user_input_update(self, tool: ToolExecution):
        """Handle tool update for user input."""
        for field in tool.user_input_schema or []:
            if not tool.tool_args:
                tool.tool_args = {}
            tool.tool_args[field.name] = field.value

    def _handle_get_user_input_tool_update(self, run_messages: RunMessages, tool: ToolExecution):
        """Handle the special get_user_input tool update."""
        import json

        if not hasattr(tool, "user_input_schema") or not tool.user_input_schema:
            return

        user_input_result = [
            {"name": user_input_field.name, "value": user_input_field.value}
            for user_input_field in tool.user_input_schema or []
        ]

        run_messages.messages.append(
            Message(
                role=self._model.tool_message_role,
                content=f"User inputs retrieved: {json.dumps(user_input_result)}",
                tool_call_id=tool.tool_call_id,
                tool_name=tool.tool_name,
                tool_args=tool.tool_args,
                metrics=Metrics(duration=0),
            )
        )

    def _reject_tool_call(
        self,
        run_messages: RunMessages,
        tool: ToolExecution,
        functions: Optional[Dict[str, Function]] = None,
    ):
        """Reject a tool call by adding an error message."""
        function_call = self._model.get_function_call_to_run_from_tool_execution(tool, functions)
        function_call.error = tool.confirmation_note or "Function call was rejected by the user"
        function_call_result = self._model.create_function_call_result(
            function_call=function_call,
            success=False,
        )
        run_messages.messages.append(function_call_result)

    async def handle_tool_call_updates(
        self,
        run_response: RunOutput,
        run_messages: RunMessages,
        tools: List[Union[Function, dict]],
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
    ):
        """Handle tool call updates for continuing a paused run (non-streaming)."""
        _functions = {tool.name: tool for tool in tools if isinstance(tool, Function)}

        for _t in run_response.tools or []:
            if (
                _t.requires_confirmation is not None
                and _t.requires_confirmation is True
                and _functions
            ):
                if _t.confirmed is not None and _t.confirmed is True and _t.result is None:
                    async for _ in self._tool_manager.run_tool(
                        run_response, run_messages, _t, functions=_functions,
                        events_to_skip=events_to_skip, store_events=store_events,
                    ):
                        pass
                else:
                    self._reject_tool_call(run_messages, _t, functions=_functions)
                    _t.confirmed = False
                    _t.confirmation_note = _t.confirmation_note or "Tool call was rejected"
                    _t.tool_call_error = True
                _t.requires_confirmation = False

            elif (
                _t.external_execution_required is not None
                and _t.external_execution_required is True
            ):
                self._handle_external_execution_update(run_messages=run_messages, tool=_t)

            elif (
                _t.tool_name == "get_user_input"
                and _t.requires_user_input is not None
                and _t.requires_user_input is True
            ):
                self._handle_get_user_input_tool_update(run_messages=run_messages, tool=_t)
                _t.requires_user_input = False
                _t.answered = True

            elif _t.requires_user_input is not None and _t.requires_user_input is True:
                self._handle_user_input_update(tool=_t)
                async for _ in self._tool_manager.run_tool(
                    run_response, run_messages, _t, functions=_functions,
                    events_to_skip=events_to_skip, store_events=store_events,
                ):
                    pass
                _t.requires_user_input = False
                _t.answered = True

    async def handle_tool_call_updates_stream(
        self,
        run_response: RunOutput,
        run_messages: RunMessages,
        tools: List[Union[Function, dict]],
        stream_events: bool = False,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
    ) -> AsyncIterator[RunOutputEvent]:
        """Handle tool call updates for continuing a paused run (streaming variant)."""
        _functions = {tool.name: tool for tool in tools if isinstance(tool, Function)}

        for _t in run_response.tools or []:
            if (
                _t.requires_confirmation is not None
                and _t.requires_confirmation is True
                and _functions
            ):
                if _t.confirmed is not None and _t.confirmed is True and _t.result is None:
                    async for event in self._tool_manager.run_tool(
                        run_response, run_messages, _t, functions=_functions,
                        stream_events=stream_events,
                        events_to_skip=events_to_skip, store_events=store_events,
                    ):
                        yield event
                else:
                    self._reject_tool_call(run_messages, _t, functions=_functions)
                    _t.confirmed = False
                    _t.confirmation_note = _t.confirmation_note or "Tool call was rejected"
                    _t.tool_call_error = True
                    if stream_events:
                        yield handle_event(
                            create_tool_call_completed_event(
                                from_run_response=run_response,
                                tool=_t,
                                content=None,
                            ),
                            run_response,
                            events_to_skip=events_to_skip,
                            store_events=store_events,
                        )
                _t.requires_confirmation = False

            elif (
                _t.external_execution_required is not None
                and _t.external_execution_required is True
            ):
                self._handle_external_execution_update(run_messages=run_messages, tool=_t)

            elif (
                _t.tool_name == "get_user_input"
                and _t.requires_user_input is not None
                and _t.requires_user_input is True
            ):
                self._handle_get_user_input_tool_update(run_messages=run_messages, tool=_t)
                _t.requires_user_input = False
                _t.answered = True

            elif _t.requires_user_input is not None and _t.requires_user_input is True:
                self._handle_user_input_update(tool=_t)
                async for event in self._tool_manager.run_tool(
                    run_response, run_messages, _t, functions=_functions,
                    stream_events=stream_events,
                    events_to_skip=events_to_skip, store_events=store_events,
                ):
                    yield event
                _t.requires_user_input = False
                _t.answered = True
