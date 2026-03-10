"""Pydantic schemas (DTOs) for session pins."""

from datetime import datetime
from typing import List
from pydantic import BaseModel


class SessionPinItem(BaseModel):
    """Model for a pin item."""

    id: str
    session_id: str
    session_name: str | None
    agent_type: str | None
    created_at: datetime
    session_created_at: datetime | None
    last_message_at: datetime | None

    class Config:
        from_attributes = True


class SessionPinResponse(BaseModel):
    """Response model for pinned sessions."""

    sessions: List[SessionPinItem]
    total: int


class PinActionResponse(BaseModel):
    """Response model for pin actions."""

    success: bool
    message: str
    session_id: str
