"""Service layer for plans domain — milestone lifecycle management."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.prompts.plan_mode_prompt import get_milestone_execution_prompt
from ii_agent.core.logger import logger
from ii_agent.plans.types import MilestoneStatus
from ii_agent.realtime.events.app_events import MilestoneUpdatedEvent
from ii_agent.realtime.events.service import EventService
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.tasks.types import RunStatus

if TYPE_CHECKING:
    from ii_agent.sessions.service import SessionService


class PlanService:
    """Orchestrates milestone execution context and status lifecycle.

    Milestones are stored in ``session.session_metadata["plan"]``.
    This service is the single source of truth for reading and mutating them.
    """

    def __init__(
        self,
        *,
        session_service: SessionService,
        event_service: EventService,
        pubsub: AsyncIOPubSub | None = None,
    ) -> None:
        self._session_service = session_service
        self._event_service = event_service
        self._pubsub = pubsub

    def set_pubsub(self, pubsub: AsyncIOPubSub) -> None:
        """Set the pubsub instance (called by lifespan after pubsub is created)."""
        self._pubsub = pubsub

    # ── Public API ────────────────────────────────────────────────────

    def get_milestone_context(
        self,
        plan_context: dict[str, Any],
        milestone_ids: list[str],
    ) -> str | None:
        """Generate AI prompt context for milestone execution."""
        try:
            summary = plan_context.get("summary", "")
            milestones = plan_context.get("milestones", [])

            if not milestones:
                return None

            milestones_text = "\n".join(
                f"  {i + 1}. [{m.get('status', 'pending').upper()}] {m.get('content', '')}"
                for i, m in enumerate(milestones)
            )

            target_milestones = [
                m for m in milestones if str(m.get("id")) in milestone_ids
            ]
            if not target_milestones:
                logger.warning(f"No milestones found matching IDs: {milestone_ids}")
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
            logger.error(f"Error getting milestone context: {e}")
            return None

    async def update_milestones_after_run(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        milestone_ids: list[str] | None,
        status: RunStatus,
    ) -> None:
        """Update milestone statuses based on run outcome."""
        if not milestone_ids:
            return

        if status == RunStatus.COMPLETED:
            await self._update_milestones_status(
                db, session_id=session_id, milestone_ids=milestone_ids, status=MilestoneStatus.COMPLETED
            )
        elif status in (RunStatus.FAILED, RunStatus.CANCELLED):
            await self._update_milestones_status(
                db, session_id=session_id, milestone_ids=milestone_ids, status=MilestoneStatus.PENDING
            )

    async def reset_milestones_to_pending(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        milestone_ids: list[str],
    ) -> None:
        """Reset milestones to pending status (used on error recovery)."""
        await self._update_milestones_status(
            db, session_id=session_id, milestone_ids=milestone_ids, status=MilestoneStatus.PENDING
        )

    # ── Private ───────────────────────────────────────────────────────

    async def _update_milestones_status(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        milestone_ids: list[str],
        status: MilestoneStatus,
    ) -> None:
        """Mutate session metadata and publish milestone events."""
        try:
            session = await self._session_service.get_session_by_id(db, session_id)
            if not session or not session.session_metadata:
                return

            plan = session.session_metadata.get("plan", {})
            milestones = plan.get("milestones", [])

            for milestone in milestones:
                if str(milestone.get("id")) not in milestone_ids:
                    continue

                milestone["status"] = str(status)

                event = MilestoneUpdatedEvent(
                    session_id=session_id,
                    content={"milestone_id": milestone.get("id"), "status": str(status)},
                    milestone_id=str(milestone.get("id", "")),
                    status=status if status in (
                        MilestoneStatus.PENDING,
                        MilestoneStatus.IN_PROGRESS,
                        MilestoneStatus.COMPLETED,
                        MilestoneStatus.FAILED,
                    ) else MilestoneStatus.PENDING,
                )
                await self._event_service.save_event(
                    db, session_id=session_id, event=event
                )
                if self._pubsub:
                    await self._pubsub.publish(event)

            updated_metadata = {**(session.session_metadata or {}), "plan": plan}
            await self._session_service.update_session_fields(
                db, session_id, session_metadata=updated_metadata
            )
            await db.commit()

        except Exception as e:
            logger.error(f"Error updating milestones status: {e}")
