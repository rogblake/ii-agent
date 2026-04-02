"""Add slide_versions table for nano banana design mode versioning

Revision ID: j3k4l5m6n7o8
Revises: i2j3k4l5m6n7
Create Date: 2026-02-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "j3k4l5m6n7o8"
down_revision: Union[str, None] = "i2j3k4l5m6n7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create slide_versions table for nano banana design mode."""
    op.create_table(
        "slide_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("presentation_name", sa.String(), nullable=False),
        sa.Column("slide_number", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("root_version_id", sa.String(), nullable=True),
        sa.Column("parent_version_id", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("edit_summary", sa.String(), nullable=True),
        sa.Column("instructions_applied", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["root_version_id"],
            ["slide_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["slide_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient queries
    op.create_index(
        "idx_slide_versions_session_id",
        "slide_versions",
        ["session_id"],
    )
    op.create_index(
        "idx_slide_versions_session_slide",
        "slide_versions",
        ["session_id", "presentation_name", "slide_number"],
    )
    op.create_index(
        "idx_slide_versions_root",
        "slide_versions",
        ["root_version_id"],
    )


def downgrade() -> None:
    """Drop slide_versions table."""
    op.drop_index("idx_slide_versions_root", table_name="slide_versions")
    op.drop_index("idx_slide_versions_session_slide", table_name="slide_versions")
    op.drop_index("idx_slide_versions_session_id", table_name="slide_versions")
    op.drop_table("slide_versions")
