import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base, TimestampColumn
from ii_agent.projects.deployments.types import DeploymentProvider, DeploymentStatus

if TYPE_CHECKING:
    from ii_agent.projects.models import Project
    from ii_agent.users.models import User


class ProjectDeployment(Base):
    """Deployment records for a project.

    Tracks individual deployments with comprehensive debugging information including:
    - Provider type (cloud_run, vercel)
    - Version numbering per project
    - Source code and build artifacts
    - Provider-specific metadata
    - Error tracking with phases
    - Performance metrics
    """

    __tablename__ = "project_deployments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    # === Existing fields (kept for backward compatibility) ===
    environment: Mapped[str] = mapped_column(String, nullable=False)
    deployment_status: Mapped[DeploymentStatus] = mapped_column(
        String, nullable=False, default=DeploymentStatus.PENDING
    )
    deployment_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    deploy_duration_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deployed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # === New fields for enhanced tracking ===

    # Deployment identification
    provider: Mapped[DeploymentProvider] = mapped_column(
        String(50),
        nullable=False,
        default=DeploymentProvider.CLOUD_RUN,
        comment="Deployment platform: cloud_run, vercel",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Auto-incrementing deployment version per project (v1, v2, v3...)",
    )
    snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Git commit SHA or version identifier of deployed code",
    )

    # Source info
    source_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Original path of source code in sandbox/workspace",
    )

    # Unified metadata for all provider-specific, source, image, and config info
    deploy_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="All deployment metadata: source, image, config, cloud_run/vercel specifics",
    )

    # Error tracking
    error_phase: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Phase where error occurred: upload, build, push, deploy, health_check",
    )
    error_details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Detailed error context: code, message, stack_trace, logs",
    )

    # Performance metrics
    upload_duration_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Time taken to upload source code to cloud storage (ms)",
    )
    build_duration_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Time taken for the build step only (ms)",
    )

    # Timestamps
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
        "Project", back_populates="deployments", foreign_keys=[project_id]
    )
    deployed_by_user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("idx_project_deployments_project_id", "project_id"),
        Index("idx_project_deployments_environment", "environment"),
        Index("idx_project_deployments_provider", "provider"),
        Index("idx_project_deployments_version", "project_id", "version"),
    )
