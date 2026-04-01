"""SQLAlchemy models for the files domain.

Unified model replacing both FileUpload and UserAsset.
Uses ``SessionAsset`` many-to-many to link files to sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ii_agent.core.db.base import Base, TimestampColumn
from ii_agent.files.types import AssetSource, AssetType, UploadStatus

if TYPE_CHECKING:
    from ii_agent.users.models import User


# ---------------------------------------------------------------------------
# FileAsset — single table for all user files
# ---------------------------------------------------------------------------


class FileAsset(Base):
    """Unified file/asset record.

    Replaces the old ``FileUpload`` (file_uploads table) and ``UserAsset``
    (user_assets table) with a single model.  The ``storage_path`` is the
    provider-relative key (e.g. ``users/<uid>/uploads/<file_id>.<ext>``).
    """

    __tablename__ = "user_assets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(
        String(20), nullable=False, default=AssetType.OTHER
    )
    source: Mapped[AssetSource] = mapped_column(
        String(30), nullable=False, default=AssetSource.USER_UPLOAD
    )
    upload_status: Mapped[UploadStatus] = mapped_column(
        String(20), nullable=False, default=UploadStatus.COMPLETE
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sandbox_path: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True, comment="Path inside the sandbox environment"
    )
    signed_url: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True, comment="Cached signed download URL"
    )
    signed_url_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the cached signed_url expires",
    )
    data: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="file_assets")
    session_links: Mapped[list["SessionAsset"]] = relationship(
        "SessionAsset", back_populates="asset", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_user_assets_user_id", "user_id"),
        Index("idx_user_assets_upload_status", "upload_status"),
    )


# ---------------------------------------------------------------------------
# SessionAsset — many-to-many link between files and sessions
# ---------------------------------------------------------------------------


class SessionAsset(Base):
    """Links a file asset to a session.

    Deleting a session cascades to ``SessionAsset`` rows but leaves the
    underlying ``FileAsset`` intact.
    """

    __tablename__ = "session_assets"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_assets.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationship back to asset
    asset: Mapped["FileAsset"] = relationship("FileAsset", back_populates="session_links")

    __table_args__ = (
        UniqueConstraint("session_id", "asset_id", name="uq_session_asset"),
        Index("idx_session_assets_session_id", "session_id"),
        Index("idx_session_assets_asset_id", "asset_id"),
    )
