"""Pydantic schemas for the plans domain."""

from __future__ import annotations

from pydantic import BaseModel

from ii_agent.plans.types import MilestoneStatus


class MilestoneSchema(BaseModel):
    """Single milestone within a plan."""

    id: str
    content: str
    details: str = ""
    status: MilestoneStatus = MilestoneStatus.PENDING
    dependencies: list[str] = []


class PlanSchema(BaseModel):
    """Project plan with milestones."""

    summary: str
    milestones: list[MilestoneSchema] = []
