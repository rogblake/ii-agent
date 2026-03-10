"""SQLAlchemy models for sessions domain.

Models migrated from core/db/models.py:
- SessionStateEnum
- Session

ChatSummary (formerly ConversationSummary) has been moved to ii_agent.chat.models (only used by chat).
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, Boolean, ForeignKey, Index, UUID
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from enum import Enum
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.auth.users.models import User
    from ii_agent.settings.llm.models import LLMSetting
    from ii_agent.projects.models import Project
    from ii_agent.agent.events.models import AgentUIEvent
    from ii_agent.files.models import FileUpload
    from ii_agent.content.slides.models import SlideContent, SlideVersion
    from ii_agent.content.storybook.models import Storybook
    from ii_agent.sessions.wishlist.models import SessionWishlist
    from ii_agent.projects.databases.models import ProjectDatabase


class SessionStateEnum(str, Enum):
    """Enum for session state values."""

    PENDING = "pending"
    ACTIVE = "active"
    PAUSE = "pause"


class Session(Base):
    """Database model for agent sessions."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    sandbox_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    llm_setting_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("llm_settings.id"),
        nullable=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    agent_state_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    agent_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    app_kind: Mapped[str] = mapped_column(String, nullable=False, default="agent", server_default="agent")
    public_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    api_version: Mapped[str] = mapped_column(String, default="v0")
    parent_session_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("sessions.id"),
        nullable=True
    )

    # Session metadata
    session_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Timestamps
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True
    )

    # Relationships (using string references)
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    llm_setting: Mapped[Optional["LLMSetting"]] = relationship(
        "LLMSetting",
        back_populates="sessions"
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        back_populates="session",
        uselist=False
    )
    events: Mapped[list["AgentUIEvent"]] = relationship(
        "AgentUIEvent",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    file_uploads: Mapped[list["FileUpload"]] = relationship(
        "FileUpload",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    slide_contents: Mapped[list["SlideContent"]] = relationship(
        "SlideContent",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    slide_versions: Mapped[list["SlideVersion"]] = relationship(
        "SlideVersion",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    storybooks: Mapped[list["Storybook"]] = relationship(
        "Storybook",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    wishlisted_by: Mapped[list["SessionWishlist"]] = relationship(
        "SessionWishlist",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    databases: Mapped[list["ProjectDatabase"]] = relationship(
        "ProjectDatabase",
        back_populates="session",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_created_at", "created_at"),
    )

    __mapper_args__ = {"version_id_col": version}

    def get_workspace_dir(self) -> str:
        """Get the workspace directory for this session."""
        from ii_agent.core.config.settings import get_settings
        settings = get_settings()
        return f"{settings.workspace_path}/{self.id}"


