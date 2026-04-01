"""Pydantic schemas (DTOs) for session wishlist."""

from datetime import datetime
from typing import List
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SessionWishlistItem(BaseModel):
    """Model for a wishlist item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    session_name: str | None
    created_at: datetime
    last_message_at: datetime | None


class SessionWishlistResponse(BaseModel):
    """Response model for wishlist sessions."""

    sessions: List[SessionWishlistItem]
    total: int


class WishlistActionResponse(BaseModel):
    """Response model for wishlist actions."""

    success: bool
    message: str
    session_id: UUID
