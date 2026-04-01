"""Pydantic schemas (DTOs) for session pins."""

from datetime import datetime
from typing import List
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SessionPinItem(BaseModel):
    """Model for a pin item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    session_name: str | None
    agent_type: str | None
    created_at: datetime
    session_created_at: datetime | None
    last_message_at: datetime | None


class SessionPinResponse(BaseModel):
    """Response model for pinned sessions."""

    sessions: List[SessionPinItem]
    total: int


class PinActionResponse(BaseModel):
    """Response model for pin actions."""

    success: bool
    message: str
    session_id: UUID
