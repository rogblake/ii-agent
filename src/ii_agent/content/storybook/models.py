"""SQLAlchemy models for storybook domain.

Models migrated from media/models.py:
- Storybook
- StorybookPageLink
- StorybookPage
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.sessions.models import Session


class Storybook(Base):
    """Database model for storybooks with versioning support."""

    __tablename__ = "storybooks"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    root_storybook_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("storybooks.id", ondelete="SET NULL"),
        nullable=True
    )
    parent_storybook_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("storybooks.id", ondelete="SET NULL"),
        nullable=True
    )
    style_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String, nullable=False, default="1:1")
    resolution: Mapped[str] = mapped_column(String, nullable=False, default="1K")
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session: Mapped["Session"] = relationship(
        "Session",
        back_populates="storybooks"
    )
    page_links: Mapped[list["StorybookPageLink"]] = relationship(
        "StorybookPageLink",
        back_populates="storybook",
        cascade="all, delete-orphan",
    )
    pages: Mapped[list["StorybookPage"]] = relationship(
        "StorybookPage",
        secondary="storybook_page_links",
        order_by="StorybookPage.page_number",
        viewonly=True,
    )
    parent: Mapped[Optional["Storybook"]] = relationship(
        "Storybook",
        remote_side=[id],
        foreign_keys=[parent_storybook_id],
        back_populates="versions",
    )
    versions: Mapped[list["Storybook"]] = relationship(
        "Storybook",
        foreign_keys=[parent_storybook_id],
        back_populates="parent",
    )

    __table_args__ = (
        Index("idx_storybooks_session_id", "session_id"),
        Index("idx_storybooks_root_id", "root_storybook_id"),
        Index("idx_storybooks_parent_id", "parent_storybook_id"),
        Index("idx_storybooks_created_at", "created_at"),
    )


class StorybookPageLink(Base):
    """Association table linking storybooks to pages (shared across versions)."""

    __tablename__ = "storybook_page_links"

    storybook_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("storybooks.id", ondelete="CASCADE"),
        primary_key=True
    )
    page_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("storybook_pages.id", ondelete="CASCADE"),
        primary_key=True
    )

    storybook: Mapped["Storybook"] = relationship(
        "Storybook",
        back_populates="page_links"
    )
    page: Mapped["StorybookPage"] = relationship(
        "StorybookPage",
        back_populates="storybook_links"
    )

    __table_args__ = (
        Index("idx_storybook_page_links_storybook_id", "storybook_id"),
        Index("idx_storybook_page_links_page_id", "page_id"),
    )


class StorybookPage(Base):
    """Database model for storybook pages with HTML content."""

    __tablename__ = "storybook_pages"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    page_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    html_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
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

    # Relationships
    storybook_links: Mapped[list["StorybookPageLink"]] = relationship(
        "StorybookPageLink",
        back_populates="page",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_storybook_pages_page_number", "page_number"),
    )
