"""SQLAlchemy models for media domain.

Only MediaTemplate belongs here. SlideContent/SlideVersion have been moved
to slides/models.py and Storybook* models to storybook/models.py.
"""

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text
from datetime import datetime, timezone
from typing import Optional

from ii_agent.core.db.base import Base, TimestampColumn



class MediaTemplate(Base):
    """ORM model for the media_templates table (templates, mini-tools, genres)."""

    __tablename__ = "media_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    preview: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )
