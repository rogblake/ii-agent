"""SQLAlchemy models for llm_settings domain."""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, Boolean, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

if TYPE_CHECKING:
    from ii_agent.auth.users.models import User
    from ii_agent.sessions.models import Session


class LLMSetting(Base):
    """Database model for LLM model settings."""

    __tablename__ = "llm_settings"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(String)
    api_type: Mapped[str] = mapped_column(String)
    encrypted_api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    max_retries: Mapped[int] = mapped_column(BigInteger, default=10)
    max_message_chars: Mapped[int] = mapped_column(BigInteger, default=30000)
    temperature: Mapped[float] = mapped_column(Float, default=1.0)
    thinking_tokens: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    llm_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="llm_settings")
    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="llm_setting")

    # Indexes
    __table_args__ = (
        Index("idx_llm_settings_user_model", "user_id", "model"),
    )
