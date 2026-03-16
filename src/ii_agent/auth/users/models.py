"""SQLAlchemy models for users domain.

- User (Main user model)
- APIKey (User API keys)

LLMSetting and MCPSetting have been moved to their owning domains:
- ii_agent.settings.llm.models.LLMSetting
- ii_agent.settings.mcp.models.MCPSetting
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, BigInteger, Boolean, Float, ForeignKey, Index, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.sessions.models import Session
    from ii_agent.settings.llm.models import LLMSetting
    from ii_agent.settings.mcp.models import MCPSetting
    from ii_agent.files.models import FileUpload
    from ii_agent.sessions.wishlist.models import SessionWishlist
    from ii_agent.sessions.pin.models import SessionPin
    from ii_agent.integrations.connectors.models import Connector, ComposioProfile
    from ii_agent.billing.models import BillingTransaction
    from ii_agent.billing.customers.models import BillingCustomer
    from ii_agent.projects.models import Project
    from ii_agent.content.skills.models import Skill


class User(Base):
    """Database model for users."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True
    )
    user_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True
    )
    login_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_plan: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_billing_cycle: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True
    )
    subscription_current_period_end: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True
    )
    credits: Mapped[float] = mapped_column(Float, default=0.0)
    bonus_credits: Mapped[float] = mapped_column(Float, default=0.0)
    language: Mapped[str] = mapped_column(String, default="en")

    # Relationships (using string references for forward declarations)
    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    llm_settings: Mapped[list["LLMSetting"]] = relationship(
        "LLMSetting",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    mcp_settings: Mapped[list["MCPSetting"]] = relationship(
        "MCPSetting",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    file_uploads: Mapped[list["FileUpload"]] = relationship(
        "FileUpload",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    session_wishlists: Mapped[list["SessionWishlist"]] = relationship(
        "SessionWishlist",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    session_pins: Mapped[list["SessionPin"]] = relationship(
        "SessionPin",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    connectors: Mapped[list["Connector"]] = relationship(
        "Connector",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    composio_profiles: Mapped[list["ComposioProfile"]] = relationship(
        "ComposioProfile",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    billing_transactions: Mapped[list["BillingTransaction"]] = relationship(
        "BillingTransaction",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    billing_customers: Mapped[list["BillingCustomer"]] = relationship(
        "BillingCustomer",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Add index for email lookup
    __table_args__ = (Index("idx_users_email", "email"),)


class APIKey(Base):
    """Database model for user API keys."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE")
    )
    api_key: Mapped[str] = mapped_column(String, unique=True)
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    # Indexes
    __table_args__ = (
        Index("idx_api_keys_user_id", "user_id"),
        Index("idx_api_keys_is_active", "is_active"),
    )
