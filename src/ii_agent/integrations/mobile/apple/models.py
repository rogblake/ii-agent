"""SQLAlchemy models for Apple mobile credentials."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import uuid

from sqlalchemy import Index, String, Text, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base, TimestampColumn


class AppleAuthState(StrEnum):
    """Apple authentication states."""

    PENDING_LOGIN = "pending_login"
    PENDING_2FA = "pending_2fa"
    PENDING_TEAM_SELECTION = "pending_team_selection"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"


class AppleCredential(Base):
    """Apple Developer credentials and session data for TestFlight deployment."""

    __tablename__ = "apple_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    apple_id: Mapped[str] = mapped_column(String)
    auth_state: Mapped[AppleAuthState] = mapped_column(
        String,
        default=AppleAuthState.PENDING_LOGIN,
    )

    encrypted_session_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_team_id: Mapped[str | None] = mapped_column(String, nullable=True)
    team_name: Mapped[str | None] = mapped_column(String, nullable=True)
    available_teams: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    session_expiry: Mapped[datetime | None] = mapped_column(
        TimestampColumn,
        nullable=True,
    )

    encrypted_expo_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_app_specific_password: Mapped[str | None] = mapped_column(Text, nullable=True)

    encrypted_ios_p12: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_ios_p12_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_ios_provisioning_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    ios_bundle_identifier: Mapped[str | None] = mapped_column(String, nullable=True)
    ios_certificate_expiry: Mapped[datetime | None] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    ios_certificate_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "apple_id", name="uq_user_apple_account"),
        Index("idx_apple_credentials_user_id", "user_id"),
    )
