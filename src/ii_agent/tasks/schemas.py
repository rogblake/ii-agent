"""Pydantic response schemas for the tasks domain."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ii_agent.tasks.types import RunStatus, TaskType


class RunTaskResponse(BaseModel):
    """Public representation of a RunTask."""

    id: UUID
    session_id: UUID
    task_type: TaskType
    status: RunStatus
    error_message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    version: int = Field(default=0)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskLogResponse(BaseModel):
    """Public representation of a TaskLog entry."""

    id: int
    task_id: UUID
    status: RunStatus
    data: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
