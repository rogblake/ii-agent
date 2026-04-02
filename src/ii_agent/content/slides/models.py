"""SQLAlchemy models for slides domain.

Models migrated from media/models.py:
- SlideContent
- SlideVersion
- SlideTemplate
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ARRAY, BigInteger, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.sessions.models import Session


class SlideContent(Base):
    """Database model for slide content storage."""

    __tablename__ = "slide_contents"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    presentation_name: Mapped[str] = mapped_column(String, nullable=False)
    slide_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    slide_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    slide_content: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Store HTML content as string
    slide_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="slide_contents")

    # Add indexes for efficient queries
    __table_args__ = (
        Index("idx_slide_contents_session_id", "session_id"),
        Index("idx_slide_contents_presentation_name", "presentation_name"),
        Index(
            "idx_slide_contents_session_presentation_slide",
            "session_id",
            "presentation_name",
            "slide_number",
            unique=True,  # Ensure uniqueness of slide within session and presentation
        ),
    )


class SlideVersion(Base):
    """Database model for slide version tracking (nano banana design mode).

    Stores version history for image-based slides, allowing users to revert
    to previous versions after making edits via AI regeneration.
    """

    __tablename__ = "slide_versions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )
    presentation_name: Mapped[str] = mapped_column(String, nullable=False)
    slide_number: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Version chain (like storybook versioning)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    root_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slide_versions.id", ondelete="SET NULL"), nullable=True
    )
    parent_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slide_versions.id", ondelete="SET NULL"), nullable=True
    )

    # Content
    image_url: Mapped[str] = mapped_column(String, nullable=False)  # GCS URL of the slide image
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Metadata
    edit_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    instructions_applied: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # List of instructions that created this version

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="slide_versions")
    parent: Mapped[Optional["SlideVersion"]] = relationship(
        "SlideVersion",
        foreign_keys=[parent_version_id],
        remote_side="SlideVersion.id",
        backref="children",
    )
    root: Mapped[Optional["SlideVersion"]] = relationship(
        "SlideVersion",
        foreign_keys=[root_version_id],
        remote_side="SlideVersion.id",
    )

    # Indexes
    __table_args__ = (
        Index("idx_slide_versions_session_id", "session_id"),
        Index(
            "idx_slide_versions_session_slide",
            "session_id",
            "presentation_name",
            "slide_number",
        ),
        Index("idx_slide_versions_root", "root_version_id"),
    )


class SlideTemplate(Base):
    """Database model for slide templates."""

    __tablename__ = "slide_templates"

    slide_template_name: Mapped[str] = mapped_column(String, nullable=False)
    slide_content: Mapped[str] = mapped_column(String, nullable=False)
    slide_template_images: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
        onupdate=func.now(),
    )

    __table_args__ = (Index("idx_slide_templates_name", "slide_template_name"),)
