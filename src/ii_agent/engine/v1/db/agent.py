from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from ii_agent.core.db.base import Base, TimestampColumn
from ii_agent.engine.v1.run.agent import RunEvent


class AgentEvent(Base):
    __tablename__ = "agent_run_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=lambda: uuid.uuid4())
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    group: Mapped[str] = mapped_column(String, nullable=False)

    name: Mapped[RunEvent] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_agent_run_events_session_id", "session_id"),
        Index("ix_agent_run_events_run_id", "run_id"),
        Index("ix_agent_run_events_session_run", "session_id", "run_id"),
        Index("ix_agent_run_events_name", "name"),
        Index("ix_agent_run_events_created_at", "created_at"),
    )
