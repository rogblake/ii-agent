"""Event models for the realtime event system."""

import enum
import time
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Index, UUID
from sqlalchemy.dialects.postgresql import JSONB

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.sessions.models import Session


class AgentStatus(str, enum.Enum):
    READY = "ready"
    RUNNING = "running"
    CANCELLED = "cancelled"


class EventType(str, enum.Enum):
    CONNECTION_ESTABLISHED = "connection_established"
    STATUS_UPDATE = "status_update"
    AGENT_INITIALIZED = "agent_initialized"
    AGENT_CONTINUE = "agent_continue"
    WORKSPACE_INFO = "workspace_info"
    PROCESSING = "processing"
    AGENT_THINKING_START = "agent_thinking_start"
    AGENT_THINKING = "agent_thinking"
    AGENT_THINKING_DELTA = "agent_thinking_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_RESPONSE = "agent_response"
    AGENT_RESPONSE_DELTA = "agent_response_delta"
    AGENT_RESPONSE_INTERRUPTED = "agent_response_interrupted"
    STREAM_COMPLETE = "stream_complete"
    ERROR = "error"
    SYSTEM = "system"
    PONG = "pong"
    UPLOAD_SUCCESS = "upload_success"
    BROWSER_USE = "browser_use"
    FILE_EDIT = "file_edit"
    USER_MESSAGE = "user_message"
    TOOL_CONFIRMATION = "tool_confirmation"
    SANDBOX_STATUS = "sandbox_status"
    COMPLETE = "complete"
    SUB_AGENT_COMPLETE = "sub_agent_complete"
    METRICS_UPDATE = "metrics_update"
    MODEL_COMPACT = "model_compact"
    PLAN_GENERATED = "plan_generated"
    MILESTONE_UPDATE = "milestone_update"
    PLAN_MODIFICATION_OPTIONS = "plan_modification_options"
    WAITING_FOR_USER_INPUT = "waiting_for_user_input"
    TESTFLIGHT_LOG = "testflight_log"
    APPLE_AUTH_STATUS = "apple_auth_status"
    APPLE_2FA_REQUIRED = "apple_2fa_required"
    APPLE_TEAM_SELECTION = "apple_team_selection"
    APPLE_APP_SETUP_STATUS = "apple_app_setup_status"
    APPLE_APPS_LIST = "apple_apps_list"
    APPLE_AUTH_CHECK_RESULT = "apple_auth_check_result"
    EXPO_TOKEN_SAVED = "expo_token_saved"
    FILE_TREE = "file_tree"
    FILE_CONTENT = "file_content"
    FILE_TREE_UPDATE = "file_tree_update"

    @staticmethod
    def is_allowed_when_aborted(event_type: "EventType") -> bool:
        return event_type in [
            EventType.STATUS_UPDATE,
            EventType.SYSTEM,
            EventType.ERROR,
            EventType.PONG,
            EventType.STREAM_COMPLETE,
            EventType.CONNECTION_ESTABLISHED,
            EventType.AGENT_RESPONSE_INTERRUPTED,
            EventType.WORKSPACE_INFO,
            EventType.SANDBOX_STATUS,
            EventType.COMPLETE,
            EventType.SUB_AGENT_COMPLETE,
        ]


class RealtimeEvent(BaseModel):
    id: _uuid.UUID = Field(default_factory=_uuid.uuid4)
    type: EventType
    session_id: _uuid.UUID | None = None
    run_id: _uuid.UUID | None = None
    run_status: str | None = None
    content: dict[str, Any]
    timestamp: float | None = Field(default_factory=time.time)


# ==================== SQLAlchemy Models ====================


class AgentUIEvent(Base):
    """Database model for session events."""

    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id", ondelete="CASCADE"))
    run_id: Mapped[Optional[_uuid.UUID]] = mapped_column(
        UUID,
        ForeignKey("agent_run_tasks.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String)
    content: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="events")

    __table_args__ = (
        Index("idx_agent_events_session_id", "session_id"),
        Index("idx_agent_events_created_at", "created_at"),
        Index("idx_agent_events_type", "type"),
    )
