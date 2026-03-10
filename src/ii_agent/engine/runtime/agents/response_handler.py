from __future__ import annotations

import json
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Type,
    Union,
    cast,
    get_args,
)
from uuid import uuid4

from ii_agent.core.logger import logger
from ii_agent.engine.runtime.media import Audio
from ii_agent.engine.runtime.models.base import Model
from ii_agent.engine.runtime.models.message import Message
from ii_agent.engine.runtime.models.metrics import Metrics
from ii_agent.engine.runtime.models.response import ModelResponse, ModelResponseEvent
from ii_agent.engine.runtime.run import RunContext
from ii_agent.engine.runtime.run.agent import (
    RunEvent,
    RunOutput,
    RunOutputEvent,
)
from ii_agent.engine.runtime.run.events import (
    create_reasoning_completed_event,
    create_reasoning_delta_event,
    create_reasoning_started_event,
    create_run_content_delta_event,
    create_run_output_content_event,
    create_sandbox_initialized_event,
    create_tool_call_completed_event,
    create_tool_call_started_event,
    handle_event,
)
from ii_agent.engine.runtime.run.messages import RunMessages
from ii_agent.engine.runtime.run.requirement import RunRequirement
from ii_agent.engine.runtime.tools.function import Function
from ii_agent.engine.runtime.utils.merge_dict import merge_dictionaries

if TYPE_CHECKING:
    from pydantic import BaseModel as PydanticBaseModel
    from ii_agent.engine.runtime.agent_sessions import AgentSession
    from ii_agent.engine.runtime.agents.sandbox_provider import SandboxProvider


class ResponseHandler:
    """Handles model response processing, streaming, and finalization."""

    def __init__(self, model: Model):
        self._model = model

    def update_run_response(
        self,
        model_response: ModelResponse,
        run_response: RunOutput,
        run_messages: RunMessages,
        run_context: Optional[RunContext] = None,
    ):
        """Update RunOutput from a non-streaming model response."""
        output_schema = run_context.output_schema if run_context else None

        if output_schema is not None and model_response.parsed is not None:
            run_response.content = model_response.parsed
            run_response.content_type = output_schema.__name__
        else:
            run_response.content = model_response.content

        if model_response.reasoning_content is not None:
            run_response.reasoning_content = model_response.reasoning_content
        if model_response.redacted_reasoning_content is not None:
            if run_response.reasoning_content is None:
                run_response.reasoning_content = model_response.redacted_reasoning_content
            else:
                run_response.reasoning_content += model_response.redacted_reasoning_content

        if model_response.citations is not None:
            run_response.citations = model_response.citations
        if model_response.provider_data is not None:
            run_response.model_provider_data = model_response.provider_data

        if model_response.tool_executions is not None:
            if run_response.tools is None:
                run_response.tools = model_response.tool_executions
            else:
                run_response.tools.extend(model_response.tool_executions)

        run_response.created_at = model_response.created_at

        self.finalize_run_response(
            run_response=run_response,
            run_messages=run_messages,
            model_response=model_response,
        )

    async def handle_model_response_stream(
        self,
        session: AgentSession,
        run_response: RunOutput,
        run_messages: RunMessages,
        tools: Optional[List[Union[Function, dict]]] = None,
        response_format: Optional[Union[Dict, Type[PydanticBaseModel]]] = None,
        stream_events: bool = False,
        session_state: Optional[Dict[str, Any]] = None,
        run_context: Optional[RunContext] = None,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        sandbox_provider: Optional[SandboxProvider] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        tool_call_limit: Optional[int] = None,
    ) -> AsyncIterator[RunOutputEvent]:
        """Handle a streaming model response, yielding events."""
        model_response = ModelResponse(content="")

        stream_model_response = True

        model_response_stream = self._model.aresponse_stream(
            messages=run_messages.messages,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            tool_call_limit=tool_call_limit,
            stream_model_response=stream_model_response,
            run_response=run_response,
        )

        async for model_response_event in model_response_stream:
            # Check if sandbox was just initialized
            if sandbox_provider is not None and sandbox_provider.was_initialized is True and sandbox_provider.sandbox:
                yield handle_event(
                    event=create_sandbox_initialized_event(
                        from_run_response=run_response,
                        sandbox_info=await sandbox_provider.sandbox.get_info(),
                    ),
                    run_response=run_response,
                    events_to_skip=events_to_skip,
                    store_events=store_events,
                )
                sandbox_provider.clear_initialized_flag()

            for event in self._handle_model_response_chunk(
                session=session,
                run_response=run_response,
                model_response=model_response,
                model_response_event=model_response_event,
                stream_events=stream_events,
                session_state=session_state,
                events_to_skip=events_to_skip,
                store_events=store_events,
                agent_id=agent_id,
                agent_name=agent_name,
            ):
                yield event

        self.finalize_run_response(
            run_response=run_response,
            run_messages=run_messages,
            model_response=model_response,
        )

    def finalize_run_response(
        self,
        run_response: RunOutput,
        run_messages: RunMessages,
        model_response: Optional[ModelResponse] = None,
    ) -> None:
        """Update RunOutput with final messages, metrics, and audio."""
        messages_for_run_response = [
            m for m in run_messages.messages if m.add_to_agent_memory and not m.from_history
        ]
        run_response.messages = messages_for_run_response
        run_response.metrics = self.calculate_run_metrics(
            messages=messages_for_run_response, current_run_metrics=run_response.metrics
        )

        if model_response is not None and model_response.audio is not None:
            run_response.response_audio = model_response.audio

    def add_fake_tool_results_for_pending_calls(
        self,
        run_messages: RunMessages,
        error_message: str,
        is_error: bool = False,
    ) -> None:
        """Add fake tool result messages for pending tool calls."""
        tool_message_role = self._model.tool_message_role if self._model else "tool"

        pending_tool_calls: List[Dict[str, Any]] = []
        for msg in run_messages.messages:
            if msg.role == self._model.assistant_message_role and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_call_id = tool_call.get("id")
                    if tool_call_id:
                        pending_tool_calls.append(tool_call)

        existing_tool_result_ids: set = set()
        for msg in run_messages.messages:
            if msg.role == tool_message_role and msg.tool_call_id:
                existing_tool_result_ids.add(msg.tool_call_id)

        for tool_call in pending_tool_calls:
            tool_call_id = tool_call.get("id")
            if tool_call_id and tool_call_id not in existing_tool_result_ids:
                function_info = tool_call.get("function", {})
                tool_name = function_info.get("name", "unknown")

                tool_args = {}
                arguments_str = function_info.get("arguments", "{}")
                try:
                    tool_args = json.loads(arguments_str) if arguments_str else {}
                except (json.JSONDecodeError, TypeError):
                    tool_args = {}

                fake_result_message = Message(
                    role=tool_message_role,
                    content=error_message,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_call_error=is_error,
                    stop_after_tool_call=True
                )
                run_messages.messages.append(fake_result_message)
                logger.debug(
                    f"Added fake tool result for pending tool call: {tool_name} ({tool_call_id})"
                )

    def calculate_run_metrics(
        self, messages: List[Message], current_run_metrics: Optional[Metrics] = None
    ) -> Metrics:
        """Sum the metrics of the given messages into a Metrics object."""
        metrics = current_run_metrics or Metrics()

        assistant_message_role = (
            self._model.assistant_message_role if self._model is not None else "assistant"
        )
        for m in messages:
            if (
                m.role == assistant_message_role
                and m.metrics is not None
                and m.from_history is False
            ):
                metrics += m.metrics

        if current_run_metrics is not None:
            metrics.timer = current_run_metrics.timer
            metrics.duration = current_run_metrics.duration
            metrics.time_to_first_token = current_run_metrics.time_to_first_token

        return metrics

    def _handle_model_response_chunk(
        self,
        session: AgentSession,
        run_response: RunOutput,
        model_response: ModelResponse,
        model_response_event: Union[ModelResponse, RunOutputEvent],
        stream_events: bool = False,
        session_state: Optional[Dict[str, Any]] = None,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> Iterator[RunOutputEvent]:
        if isinstance(model_response_event, tuple(get_args(RunOutputEvent))):
            if model_response_event.event == RunEvent.custom_event:
                model_response_event.agent_id = agent_id
                model_response_event.agent_name = agent_name
                model_response_event.session_id = session.session_id
                model_response_event.run_id = run_response.run_id

            yield handle_event(
                model_response_event,
                run_response,
                events_to_skip=events_to_skip,
                store_events=store_events,
            )
        else:
            model_response_event = cast(ModelResponse, model_response_event)
            if model_response_event.event == ModelResponseEvent.assistant_response.value:
                if model_response_event.delta_status == "reasoning_started" and stream_events:
                    model_response.reasoning_content = model_response_event.reasoning_content

                    yield handle_event(
                        create_reasoning_started_event(from_run_response=run_response),
                        run_response,
                        events_to_skip=events_to_skip,
                        store_events=store_events,
                    )

                has_reasoning = (
                    model_response_event.reasoning_content is not None
                    or model_response_event.redacted_reasoning_content is not None
                )

                if has_reasoning:
                    if (
                        model_response_event.reasoning_content is not None
                        and model_response_event.is_delta
                    ):
                        model_response.reasoning_content = (
                            model_response.reasoning_content or ""
                        ) + model_response_event.reasoning_content
                        run_response.reasoning_content = model_response.reasoning_content

                    if (
                        model_response_event.redacted_reasoning_content is not None
                        and model_response_event.is_delta
                    ):
                        if not model_response.reasoning_content:
                            model_response.reasoning_content = (
                                model_response_event.redacted_reasoning_content
                            )
                        else:
                            model_response.reasoning_content += (
                                model_response_event.redacted_reasoning_content
                            )
                        run_response.reasoning_content = model_response.reasoning_content

                    if stream_events and model_response_event.delta_status != "reasoning_done":
                        yield handle_event(
                            create_reasoning_delta_event(
                                from_run_response=run_response,
                                reasoning_content=model_response_event.reasoning_content,
                                redacted_reasoning_content=model_response_event.redacted_reasoning_content,
                                is_redacted=model_response_event.redacted_reasoning_content
                                is not None,
                                provider_data=model_response_event.provider_data,
                            ),
                            run_response,
                            events_to_skip=events_to_skip,
                            store_events=store_events,
                        )

                if model_response_event.delta_status == "reasoning_done" and stream_events:
                    yield handle_event(
                        create_reasoning_completed_event(
                            from_run_response=run_response,
                            content=model_response.reasoning_content,
                            provider_data=run_response.model_provider_data,
                        ),
                        run_response,
                        events_to_skip=events_to_skip,
                        store_events=store_events,
                    )

                if model_response_event.provider_data is not None:
                    run_response.model_provider_data = model_response_event.provider_data

                if model_response_event.citations is not None:
                    run_response.citations = model_response_event.citations

                if model_response_event.content is not None:
                    content_type = "str"
                    if model_response_event.is_delta:
                        model_response.content = (
                            model_response.content or ""
                        ) + model_response_event.content
                        yield handle_event(
                            create_run_content_delta_event(
                                from_run_response=run_response, content=model_response_event.content
                            ),
                            run_response,
                            events_to_skip=events_to_skip,
                            store_events=store_events,
                        )
                    else:
                        model_response.content = model_response_event.content
                        yield handle_event(
                            create_run_output_content_event(
                                from_run_response=run_response,
                                content=model_response_event.content,
                                citations=model_response_event.citations,
                                model_provider_data=model_response_event.provider_data
                                if not has_reasoning
                                else None,
                            ),
                            run_response,
                            events_to_skip=events_to_skip,
                            store_events=store_events,
                        )

                    run_response.content = model_response.content
                    run_response.content_type = content_type

                if model_response_event.audio is not None:
                    if model_response.audio is None:
                        model_response.audio = Audio(id=str(uuid4()), content=b"", transcript="")

                    if model_response_event.audio.id is not None:
                        model_response.audio.id = model_response_event.audio.id

                    if model_response_event.audio.content is not None:
                        if isinstance(model_response_event.audio.content, str):
                            try:
                                import base64
                                decoded_content = base64.b64decode(
                                    model_response_event.audio.content
                                )
                                if model_response.audio.content is None:
                                    model_response.audio.content = b""
                                model_response.audio.content += decoded_content
                            except Exception:
                                if model_response.audio.content is None:
                                    model_response.audio.content = b""
                                model_response.audio.content += (
                                    model_response_event.audio.content.encode("utf-8")
                                )
                        elif isinstance(model_response_event.audio.content, bytes):
                            if model_response.audio.content is None:
                                model_response.audio.content = b""
                            model_response.audio.content += model_response_event.audio.content

                    if model_response_event.audio.transcript is not None:
                        model_response.audio.transcript += model_response_event.audio.transcript

                    if model_response_event.audio.expires_at is not None:
                        model_response.audio.expires_at = model_response_event.audio.expires_at
                    if model_response_event.audio.mime_type is not None:
                        model_response.audio.mime_type = model_response_event.audio.mime_type
                    if model_response_event.audio.sample_rate is not None:
                        model_response.audio.sample_rate = model_response_event.audio.sample_rate
                    if model_response_event.audio.channels is not None:
                        model_response.audio.channels = model_response_event.audio.channels

                    run_response.response_audio = Audio(
                        id=model_response_event.audio.id,
                        content=model_response_event.audio.content,
                        transcript=model_response_event.audio.transcript,
                        sample_rate=model_response_event.audio.sample_rate,
                        channels=model_response_event.audio.channels,
                    )
                    run_response.created_at = model_response_event.created_at

                    yield handle_event(
                        create_run_output_content_event(
                            from_run_response=run_response,
                            response_audio=run_response.response_audio,
                        ),
                        run_response,
                        events_to_skip=events_to_skip,
                        store_events=store_events,
                    )

                if model_response_event.images is not None:
                    yield handle_event(
                        create_run_output_content_event(
                            from_run_response=run_response,
                            image=model_response_event.images[-1],
                        ),
                        run_response,
                        events_to_skip=events_to_skip,
                        store_events=store_events,
                    )

                    if model_response.images is None:
                        model_response.images = []
                    model_response.images.extend(model_response_event.images)
                    for image in model_response_event.images:
                        if run_response.images is None:
                            run_response.images = []
                        run_response.images.append(image)

            elif model_response_event.event == ModelResponseEvent.tool_call_paused.value:
                tool_executions_list = model_response_event.tool_executions
                if tool_executions_list is not None:
                    if run_response.tools is None:
                        run_response.tools = tool_executions_list
                    else:
                        run_response.tools.extend(tool_executions_list)
                    if run_response.requirements is None:
                        run_response.requirements = []
                    run_response.requirements.append(
                        RunRequirement(tool_execution=tool_executions_list[-1])
                    )

            elif (
                model_response_event.event == ModelResponseEvent.tool_call_started.value
            ):
                tool_executions_list = model_response_event.tool_executions
                if tool_executions_list is not None:
                    if run_response.tools is None:
                        run_response.tools = tool_executions_list
                    else:
                        run_response.tools.extend(tool_executions_list)

                    if stream_events:
                        for tool in tool_executions_list:
                            yield handle_event(
                                create_tool_call_started_event(
                                    from_run_response=run_response, tool=tool
                                ),
                                run_response,
                                events_to_skip=events_to_skip,
                                store_events=store_events,
                            )

            elif model_response_event.event == ModelResponseEvent.tool_call_completed.value:
                if model_response_event.updated_session_state is not None:
                    if session_state is not None:
                        merge_dictionaries(
                            session_state, model_response_event.updated_session_state
                        )
                    if (
                        session.session_data is not None
                        and session.session_data.get("session_state") is not None
                    ):
                        merge_dictionaries(
                            session.session_data["session_state"],
                            model_response_event.updated_session_state,
                        )

                if model_response_event.images is not None:
                    for image in model_response_event.images:
                        if run_response.images is None:
                            run_response.images = []
                        run_response.images.append(image)

                if model_response_event.videos is not None:
                    for video in model_response_event.videos:
                        if run_response.videos is None:
                            run_response.videos = []
                        run_response.videos.append(video)

                if model_response_event.audios is not None:
                    for audio in model_response_event.audios:
                        if run_response.audio is None:
                            run_response.audio = []
                        run_response.audio.append(audio)

                if model_response_event.files is not None:
                    for file_obj in model_response_event.files:
                        if run_response.files is None:
                            run_response.files = []
                        run_response.files.append(file_obj)

                tool_executions_list = model_response_event.tool_executions
                if tool_executions_list is not None:
                    if run_response.tools:
                        tool_call_index_map = {
                            tc.tool_call_id: i
                            for i, tc in enumerate(run_response.tools)
                            if tc.tool_call_id is not None
                        }
                        for tool_call_dict in tool_executions_list:
                            tool_call_id = tool_call_dict.tool_call_id or ""
                            index = tool_call_index_map.get(tool_call_id)
                            if index is not None:
                                run_response.tools[index] = tool_call_dict
                    else:
                        run_response.tools = tool_executions_list

                    for tool_call in tool_executions_list:
                        if stream_events:
                            yield handle_event(
                                create_tool_call_completed_event(
                                    from_run_response=run_response,
                                    tool=tool_call,
                                    content=model_response_event.content,
                                ),
                                run_response,
                                events_to_skip=events_to_skip,
                                store_events=store_events,
                            )
