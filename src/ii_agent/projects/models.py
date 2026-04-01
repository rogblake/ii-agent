"""SQLAlchemy models for projects domain.

Models migrated from core/db/models.py:
- Project
- ProjectDeployment
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.users.models import User
    from ii_agent.sessions.models import Session
    from ii_agent.projects.deployments.models import ProjectDeployment
    from ii_agent.projects.subdomains.models import ProjectCustomDomain


class Project(Base):
    """Projects group user resources, storage, secrets, and deployments."""

    __tablename__ = "projects"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    current_build_status: Mapped[str] = mapped_column(String, default="pending")
    framework: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    project_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    production_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    database_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    storage_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    secrets_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="projects")
    session: Mapped[Optional["Session"]] = relationship(
        "Session", back_populates="project", uselist=False
    )
    deployments: Mapped[list["ProjectDeployment"]] = relationship(
        "ProjectDeployment",
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="ProjectDeployment.project_id",
    )
    custom_domain: Mapped[Optional["ProjectCustomDomain"]] = relationship(
        "ProjectCustomDomain",
        back_populates="project",
        uselist=False,
        foreign_keys="ProjectCustomDomain.project_id",
    )

    # Indexes
    __table_args__ = (
        Index("idx_projects_user_id", "user_id"),
        Index("idx_projects_session_id", "session_id"),
        Index("idx_projects_status", "status"),
        UniqueConstraint("session_id", name="uq_projects_session_id"),
    )
