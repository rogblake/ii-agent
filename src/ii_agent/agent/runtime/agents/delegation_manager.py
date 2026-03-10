from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    List,
    Optional,
    Union,
    cast,
)

from ii_agent.core.logger import logger
from ii_agent.core.redis import raise_if_cancelled
from ii_agent.agent.runtime.run import RunContext, RunStatus
from ii_agent.agent.runtime.run.agent import RunOutput, RunOutputEvent
from ii_agent.agent.runtime.run.events import create_run_error_event
from ii_agent.agent.runtime.tools.function import Function
from ii_agent.agent.runtime.utils.merge_dict import merge_dictionaries

if TYPE_CHECKING:
    from ii_agent.agent.runtime.agent_sessions import AgentSession, SessionStore


class DelegationManager:
    """Manages sub-agent delegation."""

    def __init__(self, session_store: Optional[SessionStore] = None):
        self._session_store = session_store

    def initialize_sub_agent(self, sub_agent: Any) -> None:
        """Initialize a sub-agent with shared context from parent."""
        from ii_agent.agent.runtime.agent_sessions.base import NoOpSessionStore
        if sub_agent.session_store is None or isinstance(sub_agent.session_store, NoOpSessionStore):
            sub_agent.session_store = self._session_store

    def find_sub_agent_by_id(self, sub_agents: List, member_id: str) -> Optional[Any]:
        """Find a sub-agent by ID or name."""
        if not sub_agents:
            return None
        for agent in sub_agents:
            if agent.id == member_id or agent.name == member_id:
                return agent
        return None

    def get_sub_agents_description(self, sub_agents: List) -> str:
        """Get formatted description of sub-agents for system prompt."""
        if not sub_agents:
            return ""

        lines = ["## Available Sub-Agents\n"]
        for agent in sub_agents:
            agent_id = agent.id or agent.name
            lines.append(f"### {agent.name} (ID: {agent_id})")
            if agent.role:
                lines.append(f"**Role**: {agent.role}")
            if agent.description:
                lines.append(f"**Description**: {agent.description}")
            lines.append("")

        return "\n".join(lines)

    def get_delegate_task_function(
        self,
        sub_agents: List,
        run_response: RunOutput,
        run_context: RunContext,
        session: AgentSession,
        parent_agent: Any,
        user_id: Optional[str] = None,
        stream: bool = False,
        stream_events: bool = False,
        delegate_to_all_members: bool = False,
        stream_member_events: bool = True,
        store_member_responses: bool = False,
        **kwargs: Any,
    ) -> Function:
        """Create delegation function as a tool for the model."""
        parent_run_id = run_response.run_id
        parent_session_id = session.session_id
        delegation_mgr = self

        async def adelegate_task_to_member(
            member_id: str,
            task: str,
        ) -> AsyncIterator[Union[RunOutputEvent, RunOutput]]:
            """Delegate a task to a specific sub-agent."""
            sub_agent = delegation_mgr.find_sub_agent_by_id(sub_agents, member_id)
            if sub_agent is None:
                available = [a.id or a.name for a in sub_agents]
                yield create_run_error_event(
                    from_run_response=run_response,
                    error=f"Sub-agent with ID '{member_id}' not found. Available: {available}",
                )
                return

            member_session_state = dict(run_context.session_state or {})

            if stream:
                sub_agent_stream = await sub_agent.arun(
                    run_id=parent_run_id,
                    input=task,
                    user_id=user_id,
                    session_id=parent_session_id,
                    session_state=member_session_state,
                    stream=True,
                    stream_events=stream_events or stream_member_events,
                    yield_run_output=True,
                    is_sub_agent=True,
                    **kwargs,
                )

                async for event in sub_agent_stream:
                    event.parent_run_id = parent_run_id
                    event.delegated_from = parent_agent.name
                    if isinstance(event, RunOutput):
                        if event.status == RunStatus.ABORTED:
                            await raise_if_cancelled(parent_run_id)

                        if store_member_responses:
                            run_response.add_member_run(event)

                        if event.session_state:
                            merge_dictionaries(
                                run_context.session_state or {},
                                event.session_state,
                            )
                        continue
                    else:
                        event.is_sub_agent_event = True

                    yield event

                await raise_if_cancelled(parent_run_id)
            else:
                sub_agent_response = await sub_agent.arun(
                    run_id=parent_run_id,
                    input=task,
                    user_id=user_id,
                    session_id=parent_session_id,
                    session_state=member_session_state,
                    stream=False,
                    is_sub_agent=True,
                    **kwargs,
                )
                sub_agent_response = cast(RunOutput, sub_agent_response)

                await raise_if_cancelled(parent_run_id)

                if sub_agent_response.status == RunStatus.ABORTED:
                    await raise_if_cancelled(parent_run_id)

                sub_agent_response.parent_run_id = parent_run_id
                sub_agent_response.delegated_from = parent_agent.name

                if store_member_responses:
                    run_response.add_member_run(sub_agent_response)

                yield sub_agent_response

        async def adelegate_task_to_all_members(
            task: str,
        ) -> AsyncIterator[Union[RunOutputEvent, RunOutput]]:
            """Delegate a task to ALL sub-agents sequentially."""
            for sub_agent in sub_agents:
                member_id = sub_agent.id or sub_agent.name
                async for event in adelegate_task_to_member(member_id, task):
                    yield event

        sub_agents_description = self.get_sub_agents_description(sub_agents)

        if delegate_to_all_members:
            delegate_func = Function.from_callable(
                adelegate_task_to_all_members,
                name="sub_agent_task_all",
            )
            delegate_func.description = (
                "Delegate a task to ALL sub-agents and get combined results. All available sub-agents:\n"
                f"{sub_agents_description}"
            )
        else:
            delegate_func = Function.from_callable(
                adelegate_task_to_member,
                name="sub_agent_task",
            )
            delegate_func.description = (
                f"Delegate a task to a specific sub-agent. Available sub-agents:\n{sub_agents_description}"
            )

        delegate_func.stop_after_tool_call = False
        delegate_func.show_result = True

        return delegate_func
