"""SQLAlchemy models for subdomains domain."""

import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base, TimestampColumn

if TYPE_CHECKING:
    from ii_agent.projects.models import Project
    from ii_agent.projects.deployments.models import ProjectDeployment
    from ii_agent.auth.users.models import User


class ProjectCustomDomain(Base):
    """Custom domain records for projects.

    Allows users to claim custom subdomains that link to their project deployments.
    One custom domain per project.
    """

    __tablename__ = "project_custom_domains"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="Project this custom domain belongs to",
    )

    # Domain info
    subdomain: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        unique=True,
        comment="User-chosen subdomain (max 63 chars per DNS spec)",
    )
    full_domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Complete domain including base domain",
    )

    # Deployment linking
    deployment_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("project_deployments.id", ondelete="SET NULL"),
        nullable=True,
        comment="Specific deployment this domain points to (NULL = current production)",
    )

    # DNS/SSL status
    dns_status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        comment="DNS record status: pending, propagating, active, failed",
    )
    ssl_status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        comment="SSL certificate status: pending, provisioning, active, failed",
    )
    cloudflare_record_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Cloudflare DNS record ID for management",
    )

    # Ownership & audit
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
        comment="When the subdomain was claimed",
    )
    claimed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who claimed this subdomain",
    )

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project", back_populates="custom_domain", foreign_keys=[project_id]
    )
    deployment: Mapped[Optional["ProjectDeployment"]] = relationship("ProjectDeployment")
    claimed_by_user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("idx_project_custom_domains_project_id", "project_id"),
        Index("idx_project_custom_domains_subdomain", "subdomain"),
    )
