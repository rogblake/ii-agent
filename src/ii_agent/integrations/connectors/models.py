"""SQLAlchemy models for connectors domain.

Models migrated from core/db/models.py:
- ConnectorTypeEnum
- Connector
- ComposioProfile
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from enum import Enum
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.auth.users.models import User


class ConnectorTypeEnum(str, Enum):
    """Enum for connector types."""

    GOOGLE_DRIVE = "google_drive"
    GITHUB = "github"
    CHATGPT_MCP = "chatgpt_mcp"
    COMPOSIO = "composio"


class Connector(Base):
    """Database model for external service connectors."""

    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    connector_type: Mapped[str] = mapped_column(String)
    access_token: Mapped[str] = mapped_column(String)
    refresh_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True
    )
    connector_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True
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
    user: Mapped["User"] = relationship("User", back_populates="connectors")

    # Indexes
    __table_args__ = (
        Index("idx_connectors_user_id", "user_id"),
        Index("idx_connectors_type", "connector_type"),
        UniqueConstraint("user_id", "connector_type", name="uq_user_connector_type"),
    )


class ComposioProfile(Base):
    """Stores Composio toolkit connections with encrypted MCP URLs."""

    __tablename__ = "composio_profiles"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True
    )
    profile_name: Mapped[str] = mapped_column(String, nullable=False)  # User-friendly name
    toolkit_slug: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # "gmail", "slack", etc.
    toolkit_name: Mapped[str] = mapped_column(String, nullable=False)  # Display name

    # Composio identifiers
    auth_config_id: Mapped[str] = mapped_column(String, nullable=False)
    connected_account_id: Mapped[str] = mapped_column(String, nullable=False)
    mcp_server_id: Mapped[str] = mapped_column(String, nullable=False)
    composio_user_id: Mapped[str] = mapped_column(String, nullable=False)

    # Encrypted MCP URL and OAuth redirect URL
    encrypted_mcp_url: Mapped[str] = mapped_column(String, nullable=False)
    redirect_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        String, default="pending", nullable=False
    )  # Values: 'enable', 'disable', 'disconnected', 'pending'
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Tool configuration
    enabled_tools: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="composio_profiles")

    __table_args__ = (
        UniqueConstraint("user_id", "profile_name", name="uq_composio_profile_name"),
    )
