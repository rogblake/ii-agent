"""Service for plan-mode business logic.

Extracts plan checking, data retrieval, persistence, and task-failure
handling out of the PlanHandler so the handler becomes a thin transport
layer.
"""

from __future__ import annotations

import uuid
import logging
from typing import TYPE_CHECKING, Any

from ii_agent.agent.runs.models import RunStatus
from ii_agent.core.config.settings import Settings
from ii_agent.core.db.manager import get_db_session_local
from ii_agent.agent.events.models import EventType, RealtimeEvent

if TYPE_CHECKING:
    from ii_agent.agent.runs.service import AgentRunService
    from ii_agent.agent.events.service import EventService
    from ii_agent.agent.events.stream import EventStream
    from ii_agent.sessions.schemas import SessionInfo
    from ii_agent.sessions.service import SessionService

logger = logging.getLogger(__name__)


class PlanService:
    """Business logic for plan-mode operations."""

    def __init__(self, *, config: Settings) -> None:
        self._config = config

    # ── Plan checking ────────────────────────────────────────────────

    async def has_existing_plan(
        self,
        session_id: uuid.UUID,
        *,
        session_service: SessionService,
    ) -> bool:
        """Return ``True`` if the session has a non-empty stored plan."""
        try:
            async with get_db_session_local() as db:
                session = await session_service.get_session_by_id(
                    db, session_id=session_id
                )
                if not session or not session.session_metadata:
                    return False
                plan = session.session_metadata.get("plan")
                if not isinstance(plan, dict):
                    return False
                milestones = plan.get("milestones")
                return isinstance(milestones, list) and len(milestones) > 0
        except Exception:
            return False

    # ── Plan data retrieval ──────────────────────────────────────────

    async def get_plan_data(
        self,
        session_id: uuid.UUID,
        *,
        session_service: SessionService,
    ) -> dict | None:
        """Retrieve the current plan from session metadata.

        Returns the plan dict or ``None`` if no plan is stored.
        """
        async with get_db_session_local() as db:
            session = await session_service.get_session_by_id(
                db, session_id=session_id
            )
            if not session or not session.session_metadata:
                return None
            plan_data = session.session_metadata.get("plan", {})
            return plan_data if plan_data else None

    # ── Plan persistence ─────────────────────────────────────────────

    async def save_and_emit_plan(
        self,
        session_info: SessionInfo,
        plan_data: dict,
        *,
        session_service: SessionService,
        event_service: EventService,
    ) -> list[RealtimeEvent]:
        """Save plan to session metadata, create PLAN_GENERATED event.

        Returns the list of events the handler should emit.
        """
        events: list[RealtimeEvent] = []

        async with get_db_session_local() as db:
            session = await session_service.get_session_by_id(
                db, session_id=str(session_info.id)
            )
            if session:
                session.session_metadata = {
                    **(session.session_metadata or {}),
                    "plan": plan_data,
                }
                db.add(session)

                plan_event = RealtimeEvent(
                    type=EventType.PLAN_GENERATED,
                    session_id=session_info.id,
                    content={
                        "summary": plan_data.get("summary", ""),
                        "milestones": plan_data.get("milestones", []),
                    },
                )

                await event_service.save_event(db, session_info.id, plan_event)
                await db.commit()

                events.append(plan_event)

        logger.info("Plan submitted successfully for session %s", session_info.id)
        return events

    # ── Task failure ─────────────────────────────────────────────────

    async def fail_task(
        self,
        task_id: uuid.UUID,
        *,
        agent_run_service: AgentRunService,
    ) -> None:
        """Mark a task as FAILED.  Consolidates the repeated pattern."""
        async with get_db_session_local() as db:
            await agent_run_service.update_task_status(
                db, task_id=task_id, status=RunStatus.FAILED
            )
            await db.commit()


__all__ = ["PlanService"]
