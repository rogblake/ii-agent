"""Unit tests for PlanService."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.plans.service import PlanService
from ii_agent.plans.types import MilestoneStatus
from ii_agent.tasks.types import RunStatus


def _make_plan_service() -> tuple[PlanService, MagicMock, MagicMock, AsyncMock]:
    """Create PlanService with mocked dependencies."""
    session_svc = MagicMock()
    event_repo = MagicMock()
    pubsub = AsyncMock()

    svc = PlanService(
        session_service=session_svc,
        event_repo=event_repo,
        pubsub=pubsub,
    )
    return svc, session_svc, event_repo, pubsub


def _session_with_plan(
    summary: str = "Build a todo app",
    milestones: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock session with plan in session_metadata."""
    if milestones is None:
        milestones = [
            {"id": "1", "content": "Setup project", "details": "Init repo", "status": "pending"},
            {"id": "2", "content": "Add auth", "details": "JWT login", "status": "pending"},
            {"id": "3", "content": "Add todos", "details": "CRUD", "status": "completed"},
        ]
    session = MagicMock()
    session.session_metadata = {"plan": {"summary": summary, "milestones": milestones}}
    return session


class TestGetMilestoneContext:
    def test_single_milestone_returns_execution_prompt(self) -> None:
        svc, *_ = _make_plan_service()
        ctx = {"summary": "Build a todo app", "milestones": [
            {"id": "1", "content": "Setup project", "details": "Init repo", "status": "pending"},
        ]}
        result = svc.get_milestone_context(plan_context=ctx, milestone_ids=["1"])

        assert result is not None
        assert "Setup project" in result
        assert "Init repo" in result

    def test_multiple_milestones_returns_combined_context(self) -> None:
        svc, *_ = _make_plan_service()
        ctx = {"summary": "Build a todo app", "milestones": [
            {"id": "1", "content": "Setup project", "details": "Init repo", "status": "pending"},
            {"id": "2", "content": "Add auth", "details": "JWT login", "status": "pending"},
        ]}
        result = svc.get_milestone_context(plan_context=ctx, milestone_ids=["1", "2"])

        assert result is not None
        assert "Setup project" in result
        assert "Add auth" in result
        assert "Target Milestones to Build" in result

    def test_no_matching_milestones_returns_none(self) -> None:
        svc, *_ = _make_plan_service()
        ctx = {"summary": "Test", "milestones": [
            {"id": "1", "content": "Setup", "details": "", "status": "pending"},
        ]}
        result = svc.get_milestone_context(plan_context=ctx, milestone_ids=["99"])
        assert result is None

    def test_empty_plan_context_returns_none(self) -> None:
        svc, *_ = _make_plan_service()
        result = svc.get_milestone_context(plan_context={}, milestone_ids=["1"])
        assert result is None


class TestUpdateMilestonesAfterRun:
    @pytest.mark.asyncio
    async def test_completed_run_marks_milestones_completed(self) -> None:
        svc, session_svc, event_repo, pubsub = _make_plan_service()
        session_id = uuid.uuid4()

        session = _session_with_plan(milestones=[
            {"id": "1", "content": "Setup", "details": "", "status": "in_progress"},
        ])
        session_svc.get_session_by_id = AsyncMock(return_value=session)
        event_repo.save_event = AsyncMock()

        db = AsyncMock()
        await svc.update_milestones_after_run(
            db, session_id=session_id, milestone_ids=["1"], status=RunStatus.COMPLETED
        )

        m1 = session.session_metadata["plan"]["milestones"][0]
        assert m1["status"] == "completed"
        assert pubsub.publish.called

    @pytest.mark.asyncio
    async def test_failed_run_resets_milestones_to_pending(self) -> None:
        svc, session_svc, event_repo, pubsub = _make_plan_service()
        session_id = uuid.uuid4()

        session = _session_with_plan(milestones=[
            {"id": "1", "content": "Setup", "details": "", "status": "in_progress"},
        ])
        session_svc.get_session_by_id = AsyncMock(return_value=session)
        event_repo.save_event = AsyncMock()

        db = AsyncMock()
        await svc.update_milestones_after_run(
            db, session_id=session_id, milestone_ids=["1"], status=RunStatus.FAILED
        )

        m1 = session.session_metadata["plan"]["milestones"][0]
        assert m1["status"] == "pending"

    @pytest.mark.asyncio
    async def test_none_milestone_ids_is_noop(self) -> None:
        svc, session_svc, *_ = _make_plan_service()
        db = AsyncMock()

        await svc.update_milestones_after_run(
            db, session_id=uuid.uuid4(), milestone_ids=None, status=RunStatus.COMPLETED
        )
        session_svc.get_session_by_id.assert_not_called()


class TestResetMilestonesToPending:
    @pytest.mark.asyncio
    async def test_resets_specified_milestones(self) -> None:
        svc, session_svc, event_repo, pubsub = _make_plan_service()
        session_id = uuid.uuid4()

        session = _session_with_plan(milestones=[
            {"id": "1", "content": "Setup", "details": "", "status": "in_progress"},
            {"id": "2", "content": "Auth", "details": "", "status": "in_progress"},
        ])
        session_svc.get_session_by_id = AsyncMock(return_value=session)
        event_repo.save_event = AsyncMock()

        db = AsyncMock()
        await svc.reset_milestones_to_pending(db, session_id=session_id, milestone_ids=["1", "2"])

        for m in session.session_metadata["plan"]["milestones"]:
            assert m["status"] == "pending"
