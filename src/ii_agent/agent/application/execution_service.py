"""Service for agent execution orchestration.

Extracts task-creation, milestone-context building, and milestone-status
updates out of the socket command handlers so they become thin transport
layers.
"""

from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ii_agent.agent.runs.models import AgentRunTask, RunStatus
from ii_agent.core.config.settings import Settings
from ii_agent.core.redis import lock
from ii_agent.core.events.models import EventType, RealtimeEvent
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.agent.prompts.plan_mode_prompt import get_milestone_execution_prompt

if TYPE_CHECKING:
    from ii_agent.agent.runs.service import AgentRunService
    from ii_agent.core.events.service import EventService
    from ii_agent.sessions.service import SessionService
    from ii_agent.sessions.schemas import SessionInfo

logger = logging.getLogger(__name__)


@dataclass
class TaskCreationResult:
    """Returned by :meth:`ExecutionService.create_task_with_lock`."""

    task: AgentRunTask
    user_event: RealtimeEvent
    processing_event: RealtimeEvent


class ExecutionService:
    """Business logic that was previously duplicated across handlers."""

    def __init__(self, *, config: Settings) -> None:
        self._config = config

    # ── Task creation ────────────────────────────────────────────────

    async def create_task_with_lock(
        self,
        session_id: uuid.UUID,
        user_message_content: dict[str, Any],
        *,
        agent_run_service: AgentRunService,
        event_service: EventService,
    ) -> TaskCreationResult | None:
        """Create a task under a Redis session lock.

        Checks for an already-running task, saves the user-message event,
        creates an ``AgentRunTask``, and returns the events the handler should
        emit.  Returns ``None`` if there is already a running task.

        The handler remains responsible for calling ``send_event()`` on the
        returned events so that transport concerns stay out of this service.
        """
        lock_instance = lock.LockFactory.get_lock(
            f"session_{session_id}", timeout=60, namespace="session"
        )

        async with lock_instance:
            async with get_db_session_local() as db:
                existing_task = await agent_run_service.get_running_task(
                    db, session_id=session_id
                )
                if existing_task:
                    logger.info(
                        "Already running task for session %s, task: %s",
                        session_id,
                        existing_task.id,
                    )
                    return None

                user_event = RealtimeEvent(
                    session_id=session_id,
                    type=EventType.USER_MESSAGE,
                    content=user_message_content,
                )
                saved_user_event = await event_service.save_event(
                    db, session_id, user_event
                )

                running_task = await agent_run_service.create_task(
                    db,
                    session_id=session_id,
                    user_message_id=saved_user_event.id,
                )
                saved_user_event.run_id = running_task.id
                await db.commit()

        processing_event = RealtimeEvent(
            type=EventType.PROCESSING,
            session_id=session_id,
            run_id=running_task.id,
            content={"message": "Processing your message..."},
        )

        return TaskCreationResult(
            task=running_task,
            user_event=user_event,
            processing_event=processing_event,
        )

    # ── Milestone context ────────────────────────────────────────────

    @staticmethod
    def get_milestone_context(
        milestone_ids: list[str],
        plan_context: dict[str, Any],
    ) -> str | None:
        """Generate milestone execution context from plan data.

        Pure function — no DB or I/O.
        """
        try:
            summary = plan_context.get("summary", "")
            milestones = plan_context.get("milestones", [])

            milestones_text = "\n".join(
                f"  {i + 1}. [{m.get('status', 'pending').upper()}] {m.get('content', '')}"
                for i, m in enumerate(milestones)
            )

            target_milestones = [
                m for m in milestones if str(m.get("id")) in milestone_ids
            ]
            if not target_milestones:
                logger.warning("No milestones found matching IDs: %s", milestone_ids)
                return None

            if len(target_milestones) == 1:
                milestone = target_milestones[0]
                return get_milestone_execution_prompt(
                    plan_summary=summary,
                    all_milestones=milestones_text,
                    milestone_id=str(milestone.get("id")),
                    milestone_content=milestone.get("content", ""),
                    milestone_details=milestone.get("details", ""),
                )

            target_list = "\n".join(
                f"  - {m.get('content', '')}: {m.get('details', '')}"
                for m in target_milestones
            )
            return f"""# Project Plan Execution

**Project Summary:**
{summary}

**All Milestones:**
{milestones_text}

**Target Milestones to Build:**
{target_list}

**Task:** Build the target milestones listed above. Work through each milestone systematically, ensuring all features are implemented, tested, and integrated.

**Important:**
- Follow the milestone dependencies and order
- Ensure each milestone is fully completed before moving on
- Test each feature as you build it
- Keep the user informed of progress through each milestone
"""

        except Exception as e:
            logger.error("Error getting milestone context: %s", e)
            return None

    # ── Milestone status updates ─────────────────────────────────────

    async def update_milestones_after_run(
        self,
        session_id: uuid.UUID,
        milestone_ids: list[str] | None,
        status: RunStatus,
        *,
        session_service: SessionService,
        event_service: EventService,
    ) -> list[RealtimeEvent]:
        """Update milestone status based on task outcome.

        Returns the list of events the handler should emit.
        """
        if not milestone_ids:
            return []

        if status == RunStatus.COMPLETED:
            return await self._update_milestones_status(
                session_id, milestone_ids, "completed",
                session_service=session_service,
                event_service=event_service,
            )
        elif status in (RunStatus.FAILED, RunStatus.ABORTED):
            return await self._update_milestones_status(
                session_id, milestone_ids, "pending",
                session_service=session_service,
                event_service=event_service,
            )
        return []

    async def _update_milestones_status(
        self,
        session_id: uuid.UUID,
        milestone_ids: list[str],
        status: str,
        *,
        session_service: SessionService,
        event_service: EventService,
    ) -> list[RealtimeEvent]:
        """Update status for multiple milestones and return events to emit."""
        events: list[RealtimeEvent] = []
        try:
            session_uuid = (
                uuid.UUID(str(session_id))
                if not isinstance(session_id, uuid.UUID)
                else session_id
            )

            async with get_db_session_local() as db:
                session = await session_service.get_session_by_id(
                    db, session_id=session_id
                )
                if not session or not session.session_metadata:
                    return events

                plan = session.session_metadata.get("plan", {})
                milestones = plan.get("milestones", [])

                for milestone in milestones:
                    if str(milestone.get("id")) not in milestone_ids:
                        continue

                    milestone["status"] = status

                    milestone_event = RealtimeEvent(
                        type=EventType.MILESTONE_UPDATE,
                        session_id=session_uuid,
                        content={
                            "milestone_id": milestone.get("id"),
                            "status": status,
                        },
                    )
                    await event_service.save_event(db, session_uuid, milestone_event)
                    events.append(milestone_event)

                session.session_metadata = {
                    **session.session_metadata,
                    "plan": plan,
                }
                db.add(session)
                await db.commit()

        except Exception as e:
            logger.error("Error updating milestones status: %s", e)

        return events


__all__ = ["ExecutionService", "TaskCreationResult"]
