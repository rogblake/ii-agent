"""V1 MilestoneTool for submitting project plans with milestones."""

import uuid
from typing import Any, Callable, Awaitable, Optional, TYPE_CHECKING

from ii_agent.agents.tools.base import BaseAgentTool, ToolResult
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.realtime.pubsub import AsyncIOPubSub as EventStream
    from ii_agent.sessions.schemas import SessionInfo

class MilestoneTool(BaseAgentTool):
    """V1 Tool for submitting project plans with milestones.

    This tool is used in plan mode to submit structured plans.
    It directly saves the plan to the database and emits events.
    """

    name = "submit_plan"
    description = """Submit a project plan with milestones. Use this tool when you have
    analyzed the user's request and are ready to propose a structured implementation plan.

    Call this tool ONCE with the complete plan including:
    - A summary of the overall project
    - A list of milestones with content and details
    """
    read_only = False
    display_name = "Submit Plan"
    # Stop agent after plan submission - plan is ready for user review
    stop_after_tool_call = True

    input_schema = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A concise summary of the project plan (1-3 sentences)",
            },
            "milestones": {
                "type": "array",
                "description": "List of milestones to complete the project",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique identifier for this milestone",
                        },
                        "content": {
                            "type": "string",
                            "description": "Brief title/description of what this milestone accomplishes",
                        },
                        "details": {
                            "type": "string",
                            "description": "Detailed explanation of implementation steps",
                        },
                    },
                    "required": ["id", "content", "details"],
                },
                "minItems": 1,
                "maxItems": 10,
            },
        },
        "required": ["summary", "milestones"],
    }

    def __init__(
        self,
        session_id: uuid.UUID,
        on_plan_submit: Optional[Callable[[dict], Awaitable[None]]] = None,
        event_stream: Optional["EventStream"] = None,
        session_info: Optional["SessionInfo"] = None,
    ):
        """Initialize the MilestoneToolV1.

        Args:
            session_id: Session ID for the current session
            on_plan_submit: Optional async callback to save and emit the plan (deprecated)
            event_stream: Optional event stream for publishing events (preferred)
            session_info: Optional session information object (preferred)
        """
        self.session_id = session_id
        self._on_plan_submit = on_plan_submit
        self._event_stream = event_stream
        self._session_info = session_info

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute the milestone tool to save and emit the plan.

        Args:
            tool_input: Dictionary containing 'summary' and 'milestones'

        Returns:
            ToolResult with success or error message
        """
        try:
            summary = tool_input.get("summary", "")
            milestones = tool_input.get("milestones", [])

            # Add status to each milestone
            for milestone in milestones:
                if "status" not in milestone:
                    milestone["status"] = "pending"

            plan_data = {
                "summary": summary,
                "milestones": milestones,
            }

            # If event_stream is provided, directly save and emit (preferred method)
            if self._event_stream is not None:
                await self._save_and_emit_plan(plan_data)
            # Otherwise, use the callback (legacy method)
            elif self._on_plan_submit is not None:
                await self._on_plan_submit(plan_data)
            else:
                raise ValueError("Either event_stream or on_plan_submit must be provided")

            logger.info(f"Plan submitted successfully for session {self.session_id}")
            return ToolResult(
                llm_content=f"Plan submitted successfully with {len(milestones)} milestones. Plan is ready for user review.",
                user_display_content={
                    "summary": summary,
                    "milestones": milestones,
                },
                is_error=False,
                is_interrupted=True,  # Stop agent loop - plan is submitted
            )

        except Exception as e:
            logger.error(f"Error submitting plan: {e}", exc_info=True)
            return ToolResult(
                llm_content=f"Error submitting plan: {str(e)}",
                is_error=True,
            )

    async def _save_and_emit_plan(self, plan_data: dict) -> None:
        """Save plan to session metadata and emit plan generated event.

        Args:
            plan_data: Dictionary containing 'summary' and 'milestones'
        """
        import uuid as _uuid
        from ii_agent.realtime.events.app_events import PlanGeneratedEvent
        from ii_agent.core.db import get_db_session_local
        from ii_agent.core.container import get_app_container

        session_uuid = (
            _uuid.UUID(self.session_id)
            if isinstance(self.session_id, str)
            else self.session_id
        )

        plan_content = {
            "summary": plan_data.get("summary", ""),
            "milestones": plan_data.get("milestones", []),
        }

        container = get_app_container()
        session_repo = container.session_service._session_repo
        event_service = container.event_service

        # Save plan to session metadata
        async with get_db_session_local() as db:
            session = await session_repo.get_by_id(db, session_uuid)
            if session:
                session.session_metadata = {
                    **(session.session_metadata or {}),
                    "plan": plan_data,
                }
                db.add(session)

                # Create and save plan generated event
                plan_event = PlanGeneratedEvent(
                    session_id=session_uuid,
                    content=plan_content,
                )

                await event_service.save_event(
                    db, session_id=session_uuid, event=plan_event
                )
                await db.commit()

        # Emit plan generated event to clients
        if self._event_stream is not None:
            await self._event_stream.publish(
                PlanGeneratedEvent(
                    session_id=session_uuid,
                    content=plan_content,
                )
            )
