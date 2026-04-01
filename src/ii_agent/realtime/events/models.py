from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base


class ApplicationEvent(Base):
    """SQLAlchemy model for the ``application_events`` table."""

    __tablename__ = "application_events"

    event_type: Mapped[str] = mapped_column(String(100))
    event_group: Mapped[str] = mapped_column(String(50))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    content: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        Index(
            "idx_app_events_session",
            "session_id",
            "created_at",
        ),
        Index(
            "idx_app_events_session_type",
            "session_id",
            "event_type",
        ),
        Index(
            "idx_app_events_run",
            "run_id",
            "created_at",
            postgresql_where=text("run_id IS NOT NULL"),
        ),
        Index(
            "idx_app_events_group",
            "event_group",
            "created_at",
        ),
        Index(
            "idx_app_events_user",
            "user_id",
            "created_at",
        ),
    )
