"""SQLAlchemy models for session pins."""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Index
from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.auth.users.models import User
    from ii_agent.sessions.models import Session


class SessionPin(Base):
    """Database model for session pins."""

    __tablename__ = "session_pins"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="session_pins")
    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="pinned_by"
    )

    # Add composite unique index to prevent duplicate pin entries
    __table_args__ = (
        Index("idx_session_pins_user_session", "user_id", "session_id", unique=True),
    )
