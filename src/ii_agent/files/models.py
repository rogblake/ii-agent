"""SQLAlchemy models for files domain.

Models migrated from core/db/models.py:
- FileUpload
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, ForeignKey
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.auth.users.models import User
    from ii_agent.sessions.models import Session


class FileUpload(Base):
    """Database model for file uploads."""

    __tablename__ = "file_uploads"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    file_name: Mapped[str] = mapped_column(String)
    file_size: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="file_uploads")
    session: Mapped[Optional["Session"]] = relationship(
        "Session",
        back_populates="file_uploads"
    )
