"""SQLAlchemy models for skills domain.

Models migrated from core/db/models.py:
- SkillSource (enum)
- Skill
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Text, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from enum import Enum
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.auth.users.models import User


class SkillSource(str, Enum):
    """Skill source types."""

    BUILTIN = "builtin"  # System-provided, stored in codebase
    GITHUB = "github"  # Installed from GitHub
    CUSTOM = "custom"  # User-created/uploaded


class Skill(Base):
    """Skills available to agents.

    - user_id = NULL -> Builtin skill (shared with everyone)
    - user_id = UUID -> User-specific skill

    Design: Hybrid storage approach
    - skill_md_content: SKILL.md text for fast prompt generation (no I/O at startup)
    - storage_uri: Full skill directory location for sandbox loading on activation
    """

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # NULL = builtin/shared, UUID = user-specific
    user_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True
    )

    # Core identity (from SKILL.md frontmatter)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)

    # Source tracking
    source: Mapped[str] = mapped_column(
        String,
        default=SkillSource.BUILTIN.value
    )
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Content & Path configuration (hybrid approach)
    skill_md_content: Mapped[str] = mapped_column(Text)
    sandbox_path: Mapped[str] = mapped_column(String)
    storage_uri: Mapped[str] = mapped_column(String)

    # Metadata (from SKILL.md frontmatter)
    allowed_tools: Mapped[Optional[List]] = mapped_column(JSONB, default=list)
    license: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    compatibility: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
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
    user: Mapped[Optional["User"]] = relationship("User", back_populates="skills")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_skills_user_name"),
        Index("idx_skills_user_id", "user_id"),
        Index("idx_skills_source", "source"),
        Index("idx_skills_enabled", "is_enabled"),
        # Partial unique index for builtin skills (user_id IS NULL)
        Index(
            "idx_skills_builtin_name_unique",
            "name",
            unique=True,
            postgresql_where=text("user_id IS NULL"),
        ),
    )
