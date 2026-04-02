"""SQLAlchemy models for auth domain.

Models migrated from core/db/models.py:
- WaitlistEntry (for gated logins)

Note: User model moved to users/models.py (users domain)
"""

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from datetime import datetime, timezone

from ii_agent.core.db.base import Base, TimestampColumn


class WaitlistEntry(Base):
    """Waitlist entries for gated logins."""

    __tablename__ = "waitlist"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )
