from __future__ import annotations

import time
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Union,
)

from pydantic import BaseModel

from ii_agent.core.logger import logger
from ii_agent.agent.runtime.media import Audio, File, Image, Video
from ii_agent.agent.runtime.models.base import Model
from ii_agent.agent.runtime.models.message import Message
from ii_agent.agent.runtime.run.agent import RunOutput
from ii_agent.agent.runtime.run.messages import RunMessages
from ii_agent.agent.runtime.tools.function import Function
from ii_agent.agent.runtime.utils.message import get_text_from_message

if TYPE_CHECKING:
    from ii_agent.agent.runtime.run import RunContext
    from ii_agent.agent.runtime.agent_sessions import AgentSession


class MessageBuilder:
    """Builds system, user, and run messages for agent execution."""

    def __init__(
        self,
        model: Model,
        system_message: Optional[Union[str, Message]],
    ):
        self._model = model
        self._system_message = system_message

    def get_agent_data(
        self,
        name: Optional[str],
        agent_id: Optional[str],
        model: Optional[Model],
    ) -> Dict[str, Any]:
        agent_data: Dict[str, Any] = {}
        if name is not None:
            agent_data["name"] = name
        if agent_id is not None:
            agent_data["agent_id"] = agent_id
        if model is not None:
            agent_data["model"] = model.to_dict()
        return agent_data

    async def get_system_message(
        self,
        session: AgentSession,
        run_context: Optional[RunContext] = None,
        user_id: Optional[str] = None,
        tools: Optional[List[Union[Function, dict]]] = None,
    ) -> Optional[Message]:
        """Return the system message for the Agent."""
        if self._system_message is not None:
            if isinstance(self._system_message, Message):
                return self._system_message
        return Message(role=self._model.system_message_role, content=self._system_message)

    async def get_user_message(
        self,
        *,
        input: Optional[Union[str, List, Dict, Message, BaseModel, List[Message]]] = None,
        audio: Optional[Sequence[Audio]] = None,
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
        files: Optional[Sequence[File]] = None,
        **kwargs: Any,
    ) -> Optional[Message]:
        """Return the user message for the Agent."""
        if input is None:
            if images is not None or audio is not None or videos is not None or files is not None:
                return Message(
                    role="user",
                    content="",
                    images=images,
                    audio=audio,
                    videos=videos,
                    files=files,
                    **kwargs,
                )
            else:
                return None
        else:
            if isinstance(input, list):
                if all(isinstance(item, str) for item in input):
                    message_content = "\n".join(input)
                else:
                    message_content = str(input)

                return Message(
                    role=self._model.user_message_role,
                    content=message_content,
                    images=images,
                    audio=audio,
                    videos=videos,
                    files=files,
                    **kwargs,
                )
            elif isinstance(input, Message):
                return input
            elif isinstance(input, dict):
                try:
                    return Message.model_validate(input)
                except Exception as e:
                    logger.warning(f"Failed to validate message: {e}")
                    raise Exception(f"Failed to validate message: {e}")
            elif isinstance(input, BaseModel):
                try:
                    content = input.model_dump_json(indent=2, exclude_none=True)
                    return Message(role="user", content=content)
                except Exception as e:
                    logger.warning(f"Failed to convert BaseModel to message: {e}")
                    raise Exception(f"Failed to convert BaseModel to message: {e}")
            else:
                user_msg_content_str = get_text_from_message(input) if input is not None else ""
                return Message(
                    role=self._model.user_message_role,
                    content=user_msg_content_str,
                    audio=audio,
                    images=images,
                    videos=videos,
                    files=files,
                    **kwargs,
                )

    async def get_run_messages(
        self,
        *,
        run_response: RunOutput,
        input: Union[str, List, Dict, Message, BaseModel, List[Message]],
        session: AgentSession,
        agent_id: Optional[str] = None,
        run_context: Optional[RunContext] = None,
        user_id: Optional[str] = None,
        audio: Optional[Sequence[Audio]] = None,
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
        files: Optional[Sequence[File]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Union[Function, dict]]] = None,
        **kwargs: Any,
    ) -> RunMessages:
        """Build the RunMessages object for a run.

        Steps:
        1. Add system message
        2. Add history or summary
        3. Add user message or input messages

        Returns:
            RunMessages with system_message, user_message, and messages list.
        """
        run_messages = RunMessages()

        # 1. Add system message
        system_message = await self.get_system_message(
            session=session,
            run_context=run_context,
            user_id=user_id,
            tools=tools,
        )
        if system_message is not None:
            run_messages.system_message = system_message
            run_messages.messages.append(system_message)

        from copy import deepcopy

        skip_role = (
            self._model.system_message_role
            if self._model.system_message_role not in ["user", "assistant", "tool"]
            else None
        )

        # If session has a summary, use it instead of history
        if run_response.summary is not None and run_response.summary.content:
            summary_message = Message(
                role="user",
                content=f"{run_response.summary.content}\n",
                is_summary=True,
                from_history=False,
                metrics=run_response.summary.metrics,
                created_at=int(run_response.summary.updated_at.timestamp()) if run_response.summary.updated_at else int(time.time()),
            )
            run_messages.messages.append(summary_message)
            logger.debug("Added session summary - skipping history (already summarized)")
        else:
            # No summary - use full history from previous runs
            history: List[Message] = session.get_messages(
                skip_roles=[skip_role] if skip_role else None, agent_id=agent_id
            )

            if len(history) > 0:
                history_copy = [deepcopy(msg) for msg in history]
                for _msg in history_copy:
                    _msg.from_history = True
                logger.debug(f"Adding {len(history_copy)} messages from history")
                run_messages.messages += history_copy

        if len(run_messages.messages) == 1 and run_messages.messages[0].role == 'system':
            if session.summary and session.summary.content:
                summary_message = Message(
                    role="user",
                    content=f"{session.summary.content}\n",
                    is_summary=True,
                    from_history=False,
                    metrics=session.summary.metrics,
                    created_at=int(session.summary.updated_at.timestamp()) if session.summary.updated_at else int(time.time()),
                )
                run_messages.messages.append(summary_message)
                logger.debug("Added session summary - skipping history (already summarized)")

        user_message: Optional[Message] = None

        if (
            input is None
            or isinstance(input, str)
            or (
                isinstance(input, list)
                and not (
                    len(input) > 0
                    and (
                        isinstance(input[0], Message)
                        or (isinstance(input[0], dict) and "role" in input[0])
                    )
                )
            )
        ):
            user_message = await self.get_user_message(
                metadata=metadata,
                input=input,
                audio=audio,
                images=images,
                videos=videos,
                files=files,
                **kwargs,
            )
        elif isinstance(input, Message):
            user_message = input
        elif isinstance(input, dict):
            try:
                user_message = Message.model_validate(input)
            except Exception as e:
                logger.warning(f"Failed to validate message: {e}")
        elif isinstance(input, BaseModel):
            try:
                content = input.model_dump_json(indent=2, exclude_none=True)
                user_message = Message(role="user", content=content)
            except Exception as e:
                logger.warning(f"Failed to convert BaseModel to message: {e}")

        # Add input messages if provided as List[Message] or List[Dict]
        if (
            isinstance(input, list)
            and len(input) > 0
            and (
                isinstance(input[0], Message) or (isinstance(input[0], dict) and "role" in input[0])
            )
        ):
            for _m in input:
                if isinstance(_m, Message):
                    run_messages.messages.append(_m)
                    if run_messages.extra_messages is None:
                        run_messages.extra_messages = []
                    run_messages.extra_messages.append(_m)
                elif isinstance(_m, dict):
                    try:
                        msg = Message.model_validate(_m)
                        run_messages.messages.append(msg)
                        if run_messages.extra_messages is None:
                            run_messages.extra_messages = []
                        run_messages.extra_messages.append(msg)
                    except Exception as e:
                        logger.warning(f"Failed to validate message: {e}")

        if user_message is not None:
            run_messages.user_message = user_message
            run_messages.messages.append(user_message)

        return run_messages

    def get_continue_run_messages(
        self,
        input: List[Message],
    ) -> RunMessages:
        """Build RunMessages for continuing a paused run."""
        run_messages = RunMessages()

        user_message = None
        for msg in reversed(input):
            if msg.role == "user":
                user_message = msg
                break

        system_message = None
        for msg in input:
            if msg.role == "system":
                system_message = msg
                break

        run_messages.system_message = system_message
        run_messages.user_message = user_message
        run_messages.messages = input

        return run_messages
