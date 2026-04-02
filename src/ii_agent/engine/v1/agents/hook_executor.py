from __future__ import annotations

from inspect import iscoroutinefunction
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    List,
    Optional,
)

from ii_agent.core.logger import logger
from ii_agent.engine.v1.exceptions import (
    InputCheckError,
    OutputCheckError,
)
from ii_agent.engine.v1.run.agent import RunEvent
from ii_agent.engine.v1.run.events import (
    create_post_hook_completed_event,
    create_post_hook_started_event,
    create_pre_hook_completed_event,
    create_pre_hook_started_event,
    handle_event,
)
from ii_agent.engine.v1.utils.hooks import filter_hook_args

if TYPE_CHECKING:
    from ii_agent.engine.v1.run import RunContext
    from ii_agent.engine.v1.run.agent import (
        RunInput,
        RunOutput,
        RunOutputEvent,
    )
    from ii_agent.engine.v1.agent_sessions import AgentSession


class HookExecutor:
    """Executes pre-hooks and post-hooks for agent runs. Stateless."""

    async def execute_pre_hooks(
        self,
        hooks: Optional[List[Callable[..., Any]]],
        run_response: RunOutput,
        run_input: RunInput,
        run_context: RunContext,
        session: AgentSession,
        agent_ref: Any,
        user_id: Optional[str] = None,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
        stream_events: bool = False,
        **kwargs: Any,
    ) -> AsyncIterator[RunOutputEvent]:
        """Execute multiple pre-hook functions in succession."""
        if hooks is None:
            return

        all_args = {
            "run_input": run_input,
            "agent": agent_ref,
            "session": session,
            "run_context": run_context,
            "session_state": run_context.session_state,
            "dependencies": run_context.dependencies,
            "metadata": run_context.metadata,
            "user_id": user_id,
        }
        all_args.update(kwargs)

        for i, hook in enumerate(hooks):
            if stream_events:
                yield handle_event(
                    run_response=run_response,
                    event=create_pre_hook_started_event(
                        from_run_response=run_response,
                        run_input=run_input,
                        pre_hook_name=hook.__name__,
                    ),
                    events_to_skip=events_to_skip,
                    store_events=store_events,
                )
            try:
                filtered_args = filter_hook_args(hook, all_args)

                if iscoroutinefunction(hook):
                    await hook(**filtered_args)
                else:
                    hook(**filtered_args)

                if stream_events:
                    yield handle_event(
                        run_response=run_response,
                        event=create_pre_hook_completed_event(
                            from_run_response=run_response,
                            run_input=run_input,
                            pre_hook_name=hook.__name__,
                        ),
                        events_to_skip=events_to_skip,
                        store_events=store_events,
                    )

            except (InputCheckError, OutputCheckError) as e:
                raise e
            except Exception as e:
                logger.error(f"Pre-hook #{i + 1} execution failed: {str(e)}")
                logger.error(e)

        # Update the input on the run_response
        run_response.input = run_input

    async def execute_post_hooks(
        self,
        hooks: Optional[List[Callable[..., Any]]],
        run_output: RunOutput,
        run_context: RunContext,
        session: AgentSession,
        agent_ref: Any,
        user_id: Optional[str] = None,
        events_to_skip: Optional[List[RunEvent]] = None,
        store_events: bool = False,
        stream_events: bool = False,
        **kwargs: Any,
    ) -> AsyncIterator[RunOutputEvent]:
        """Execute multiple post-hook functions in succession."""
        if hooks is None:
            return

        all_args = {
            "run_output": run_output,
            "agent": agent_ref,
            "session": session,
            "run_context": run_context,
            "session_state": run_context.session_state,
            "dependencies": run_context.dependencies,
            "metadata": run_context.metadata,
            "user_id": user_id,
        }
        all_args.update(kwargs)

        for i, hook in enumerate(hooks):
            if stream_events:
                yield handle_event(
                    run_response=run_output,
                    event=create_post_hook_started_event(
                        from_run_response=run_output,
                        post_hook_name=hook.__name__,
                    ),
                    events_to_skip=events_to_skip,
                    store_events=store_events,
                )
            try:
                filtered_args = filter_hook_args(hook, all_args)

                if iscoroutinefunction(hook):
                    await hook(**filtered_args)
                else:
                    hook(**filtered_args)

                if stream_events:
                    yield handle_event(
                        run_response=run_output,
                        event=create_post_hook_completed_event(
                            from_run_response=run_output,
                            post_hook_name=hook.__name__,
                        ),
                        events_to_skip=events_to_skip,
                        store_events=store_events,
                    )

            except (InputCheckError, OutputCheckError) as e:
                raise e
            except Exception as e:
                logger.error(f"Post-hook #{i + 1} execution failed: {str(e)}")
                logger.error(e)
