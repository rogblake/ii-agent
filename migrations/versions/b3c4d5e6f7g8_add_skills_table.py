"""Add skills table

Revision ID: b3c4d5e6f7g8
Revises: 67e27083b123
Create Date: 2025-12-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7g8"
down_revision: Union[str, None] = "67e27083b123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create skills table."""
    op.create_table(
        "skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="builtin"),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column(
            "skill_md_content", sa.Text(), nullable=False
        ),  # SKILL.md content for fast prompt gen
        sa.Column("sandbox_path", sa.String(), nullable=False),
        sa.Column(
            "storage_uri", sa.String(), nullable=False
        ),  # Full directory URI for sandbox
        sa.Column("allowed_tools", JSONB(), nullable=True, server_default="[]"),
        sa.Column("license", sa.String(), nullable=True),
        sa.Column("compatibility", sa.String(500), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_skills_user_name"),
    )
    op.create_index("idx_skills_user_id", "skills", ["user_id"])
    op.create_index("idx_skills_source", "skills", ["source"])
    op.create_index("idx_skills_enabled", "skills", ["is_enabled"])
    # Partial unique index for builtin skills (user_id IS NULL)
    # PostgreSQL doesn't consider NULL=NULL, so we need this for upsert to work
    op.create_index(
        "idx_skills_builtin_name_unique",
        "skills",
        ["name"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )


def downgrade() -> None:
    """Drop skills table."""
    op.drop_index("idx_skills_builtin_name_unique", table_name="skills")
    op.drop_index("idx_skills_enabled", table_name="skills")
    op.drop_index("idx_skills_source", table_name="skills")
    op.drop_index("idx_skills_user_id", table_name="skills")
    op.drop_table("skills")
