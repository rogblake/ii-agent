"""SQLAlchemy models for session wishlist."""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.users.models import User
    from ii_agent.sessions.models import Session


class SessionWishlist(Base):
    """Database model for session wishlists."""

    __tablename__ = "session_wishlists"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="session_wishlists")
    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="wishlisted_by"
    )

    # Add composite unique index to prevent duplicate wishlist entries
    __table_args__ = (
        Index("idx_session_wishlists_user_session", "user_id", "session_id", unique=True),
    )
